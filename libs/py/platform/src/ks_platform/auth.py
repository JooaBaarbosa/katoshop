import asyncio
import base64
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, cast

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import Depends, Request

from ks_platform.errors import ProblemError

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {"admin": frozenset({"*"})}

_CHALLENGE = {"WWW-Authenticate": "Bearer"}
_REQUIRED_CLAIMS = ["exp", "iat", "sub", "aud", "iss", "jti"]

type Fetch = Callable[[str], Awaitable[dict[str, Any]]]


def _invalid_token(detail: str) -> ProblemError:
    return ProblemError(
        401, "auth.invalid_token", "Token inválido", detail, headers=dict(_CHALLENGE)
    )


def _forbidden(detail: str) -> ProblemError:
    return ProblemError(403, "auth.forbidden", "Acesso negado", detail)


def _insufficient_permission(perm: str) -> ProblemError:
    # R25: código próprio para que o cliente separe falta de permissão (mantém a sessão) de
    # token emitido para outra audiência (auth.forbidden, R1: encerra a sessão)
    return ProblemError(
        403, "auth.insufficient_permission", "Permissão insuficiente", f"Requer {perm}."
    )


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    audience: Literal["storefront", "admin"]
    kind: Literal["customer", "staff"]
    roles: frozenset[str]

    def has_permission(self, perm: str) -> bool:
        for role in self.roles:
            granted = ROLE_PERMISSIONS.get(role, frozenset())
            if "*" in granted or perm in granted:
                return True
        return False


async def _default_fetch(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=2.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return cast("dict[str, Any]", response.json())


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _parse_jwks(document: dict[str, Any]) -> dict[str, Ed25519PublicKey]:
    keys: dict[str, Ed25519PublicKey] = {}
    for jwk in document.get("keys", []):
        try:
            if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519" or not jwk.get("kid"):
                continue
            keys[jwk["kid"]] = Ed25519PublicKey.from_public_bytes(_b64url_decode(jwk["x"]))
        except KeyError, TypeError, ValueError:
            continue
    return keys


class JwksKeyProvider:
    def __init__(
        self,
        jwks_url: str,
        fetch: Fetch | None = None,
        ttl_seconds: int = 300,
        min_refetch_seconds: int = 30,
    ) -> None:
        self._url = jwks_url
        self._fetch = fetch or _default_fetch
        self._ttl = ttl_seconds
        self._min_refetch = min_refetch_seconds
        self._keys: dict[str, Ed25519PublicKey] = {}
        self._loaded_at: float | None = None
        self._last_miss_at: float | None = None
        self._next_retry_at: float | None = None
        self._lock = asyncio.Lock()

    def _unavailable(self) -> ProblemError:
        return ProblemError(503, "auth.jwks_unavailable", "Chaves de autenticação indisponíveis")

    async def _load(self) -> None:
        now = time.monotonic()
        if self._next_retry_at is not None and now < self._next_retry_at:
            # Em backoff após falha: não chama o fetch, usa o cache (se houver).
            if self._keys:
                return
            raise self._unavailable()
        try:
            document = await self._fetch(self._url)
        except (httpx.HTTPError, ValueError, OSError) as exc:
            self._next_retry_at = now + self._min_refetch
            if self._keys:
                return  # mantém as chaves em cache enquanto o JWKS estiver fora
            raise self._unavailable() from exc
        self._next_retry_at = None
        self._keys = _parse_jwks(document)
        self._loaded_at = time.monotonic()

    async def get_key(self, kid: str) -> Ed25519PublicKey:
        async with self._lock:
            now = time.monotonic()
            loaded_now = False
            if self._loaded_at is None or now - self._loaded_at >= self._ttl:
                await self._load()
                loaded_now = True
            key = self._keys.get(kid)
            if key is not None:
                return key
            throttled = (
                self._last_miss_at is not None and now - self._last_miss_at < self._min_refetch
            )
            if not throttled:
                self._last_miss_at = now
                if not loaded_now:
                    await self._load()
                    key = self._keys.get(kid)
                    if key is not None:
                        return key
            raise _invalid_token("Chave de assinatura desconhecida.")


class TokenVerifier:
    def __init__(self, keys: JwksKeyProvider, issuer: str = "katoshop-identity") -> None:
        self._keys = keys
        self._issuer = issuer

    async def verify(self, token: str, audience: str) -> Principal:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError as exc:
            raise _invalid_token("Token malformado.") from exc
        if not isinstance(kid, str) or not kid:
            raise _invalid_token("Token sem kid.")
        key = await self._keys.get_key(kid)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=["EdDSA"],
                audience=audience,
                issuer=self._issuer,
                options={"require": _REQUIRED_CLAIMS},
            )
        except jwt.InvalidAudienceError as exc:
            # Assinatura e expiração já foram validadas: autenticado, mas na audiência errada.
            raise _forbidden("Token emitido para outra audiência.") from exc
        except jwt.PyJWTError as exc:
            raise _invalid_token("Token inválido ou expirado.") from exc
        return _principal_from_claims(claims)


def _principal_from_claims(claims: dict[str, Any]) -> Principal:
    try:
        user_id = uuid.UUID(claims["sub"])
    except (ValueError, TypeError) as exc:
        raise _invalid_token("Claim sub inválido.") from exc
    audience = claims["aud"]
    kind = claims.get("kind")
    roles = claims.get("roles", [])
    if (
        audience not in ("storefront", "admin")
        or kind not in ("customer", "staff")
        or not isinstance(roles, list)
        or not all(isinstance(role, str) for role in roles)
    ):
        raise _invalid_token("Claims inválidos.")
    return Principal(user_id, audience, kind, frozenset(roles))


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ProblemError(
            401,
            "auth.missing_token",
            "Autenticação necessária",
            "Envie o cabeçalho Authorization: Bearer <token>.",
            headers=dict(_CHALLENGE),
        )
    return token.strip()


def require_audience(audience: str) -> Callable[..., Awaitable[Principal]]:
    async def dependency(request: Request) -> Principal:
        verifier: TokenVerifier = request.app.state.token_verifier
        return await verifier.verify(_bearer_token(request), audience)

    return dependency


def require_permission(perm: str, audience: str = "admin") -> Callable[..., Awaitable[Principal]]:
    async def dependency(
        principal: Principal = Depends(require_audience(audience)),  # noqa: B008
    ) -> Principal:
        if not principal.has_permission(perm):
            raise _insufficient_permission(perm)
        return principal

    return dependency
