import base64
import time
import uuid
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from ks_platform.auth import (
    JwksKeyProvider,
    Principal,
    TokenVerifier,
    require_audience,
    require_permission,
)
from ks_platform.errors import ProblemError, install_problem_handlers


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class Signer:
    def __init__(self, kid: str = "k1") -> None:
        self.kid = kid
        self.private = Ed25519PrivateKey.generate()

    @property
    def jwk(self) -> dict[str, str]:
        raw = self.private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return {
            "kty": "OKP",
            "crv": "Ed25519",
            "x": _b64(raw),
            "kid": self.kid,
            "alg": "EdDSA",
            "use": "sig",
        }

    def token(
        self,
        *,
        aud: str = "admin",
        roles: list[str] | None = None,
        exp_delta: int = 900,
        kind: str = "staff",
        with_kid: bool = True,
        iss: str = "katoshop-identity",
    ) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "sub": str(uuid.uuid4()),
            "aud": aud,
            "iss": iss,
            "iat": now,
            "exp": now + exp_delta,
            "jti": str(uuid.uuid4()),
            "roles": ["admin"] if roles is None else roles,
            "kind": kind,
        }
        headers = {"kid": self.kid} if with_kid else {}
        return jwt.encode(claims, self.private, algorithm="EdDSA", headers=headers)


class FakeFetch:
    def __init__(self, *responses: dict[str, Any]) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def __call__(self, url: str) -> dict[str, Any]:
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[index]


def _verifier(fetch: FakeFetch) -> TokenVerifier:
    return TokenVerifier(JwksKeyProvider("http://identity/jwks", fetch=fetch))


async def test_valid_token_returns_principal() -> None:
    signer = Signer()
    verifier = _verifier(FakeFetch({"keys": [signer.jwk]}))
    principal = await verifier.verify(signer.token(roles=["admin"]), "admin")
    assert isinstance(principal, Principal)
    assert principal.audience == "admin"
    assert principal.kind == "staff"
    assert principal.roles == frozenset({"admin"})
    assert principal.has_permission("catalog.write") is True


async def test_expired_token_rejected() -> None:
    signer = Signer()
    verifier = _verifier(FakeFetch({"keys": [signer.jwk]}))
    with pytest.raises(ProblemError) as exc:
        await verifier.verify(signer.token(exp_delta=-60), "admin")
    assert exc.value.status == 401
    assert exc.value.code == "auth.invalid_token"
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


async def test_wrong_audience_rejected() -> None:
    signer = Signer()
    verifier = _verifier(FakeFetch({"keys": [signer.jwk]}))
    with pytest.raises(ProblemError) as exc:
        await verifier.verify(signer.token(aud="storefront", kind="customer"), "admin")
    assert exc.value.status == 403
    assert exc.value.code == "auth.forbidden"


async def test_bad_signature_rejected() -> None:
    signer, other = Signer(), Signer()
    verifier = _verifier(FakeFetch({"keys": [signer.jwk]}))
    with pytest.raises(ProblemError) as exc:
        await verifier.verify(other.token(), "admin")
    assert (exc.value.status, exc.value.code) == (401, "auth.invalid_token")


async def test_wrong_issuer_rejected() -> None:
    signer = Signer()
    verifier = _verifier(FakeFetch({"keys": [signer.jwk]}))
    with pytest.raises(ProblemError) as exc:
        await verifier.verify(signer.token(iss="evil"), "admin")
    assert (exc.value.status, exc.value.code) == (401, "auth.invalid_token")


async def test_malformed_token_rejected() -> None:
    verifier = _verifier(FakeFetch({"keys": []}))
    with pytest.raises(ProblemError) as exc:
        await verifier.verify("not-a-jwt", "admin")
    assert (exc.value.status, exc.value.code) == (401, "auth.invalid_token")


async def test_missing_kid_rejected() -> None:
    signer = Signer()
    verifier = _verifier(FakeFetch({"keys": [signer.jwk]}))
    with pytest.raises(ProblemError) as exc:
        await verifier.verify(signer.token(with_kid=False), "admin")
    assert (exc.value.status, exc.value.code) == (401, "auth.invalid_token")


async def test_alg_none_rejected() -> None:
    signer = Signer()
    verifier = _verifier(FakeFetch({"keys": [signer.jwk]}))
    forged = jwt.encode({"sub": "x", "aud": "admin"}, None, algorithm="none", headers={"kid": "k1"})  # pyright: ignore[reportArgumentType]
    with pytest.raises(ProblemError) as exc:
        await verifier.verify(forged, "admin")
    assert (exc.value.status, exc.value.code) == (401, "auth.invalid_token")


async def test_unknown_kid_refetches_once() -> None:
    k1, k2 = Signer("k1"), Signer("k2")
    fetch = FakeFetch({"keys": [k1.jwk]}, {"keys": [k1.jwk, k2.jwk]})
    verifier = _verifier(fetch)
    await verifier.verify(k1.token(), "admin")
    assert fetch.calls == 1
    principal = await verifier.verify(k2.token(), "admin")
    assert principal.has_permission("catalog.write")
    assert fetch.calls == 2


async def test_unknown_kid_refetch_is_throttled() -> None:
    k1, ghost = Signer("k1"), Signer("ghost")
    fetch = FakeFetch({"keys": [k1.jwk]})
    verifier = _verifier(fetch)
    for _ in range(2):
        with pytest.raises(ProblemError) as exc:
            await verifier.verify(ghost.token(), "admin")
        assert (exc.value.status, exc.value.code) == (401, "auth.invalid_token")
    assert fetch.calls == 1


async def test_keys_cached_within_ttl() -> None:
    signer = Signer()
    fetch = FakeFetch({"keys": [signer.jwk]})
    verifier = _verifier(fetch)
    for _ in range(3):
        await verifier.verify(signer.token(), "admin")
    assert fetch.calls == 1


async def test_fetch_failure_is_503_not_500() -> None:
    async def boom(url: str) -> dict[str, Any]:
        raise httpx.ConnectError("down")

    signer = Signer()
    verifier = TokenVerifier(JwksKeyProvider("http://identity/jwks", fetch=boom))
    with pytest.raises(ProblemError) as exc:
        await verifier.verify(signer.token(), "admin")
    assert (exc.value.status, exc.value.code) == (503, "auth.jwks_unavailable")


class FlakyFetch:
    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document
        self.calls = 0
        self.failing = False

    async def __call__(self, url: str) -> dict[str, Any]:
        self.calls += 1
        if self.failing:
            raise httpx.ConnectError("down")
        return self.document


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_stale_keys_still_verify_when_fetch_fails_after_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock()
    monkeypatch.setattr("ks_platform.auth.time.monotonic", clock)
    signer = Signer()
    fetch = FlakyFetch({"keys": [signer.jwk]})
    verifier = TokenVerifier(JwksKeyProvider("http://identity/jwks", fetch=fetch, ttl_seconds=300))
    await verifier.verify(signer.token(), "admin")
    fetch.failing = True
    clock.now += 301
    principal = await verifier.verify(signer.token(), "admin")
    assert principal.has_permission("catalog.write")
    assert fetch.calls == 2


async def test_failed_fetch_backoff_skips_fetch_with_stale_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock()
    monkeypatch.setattr("ks_platform.auth.time.monotonic", clock)
    signer = Signer()
    fetch = FlakyFetch({"keys": [signer.jwk]})
    verifier = TokenVerifier(
        JwksKeyProvider(
            "http://identity/jwks", fetch=fetch, ttl_seconds=300, min_refetch_seconds=30
        )
    )
    await verifier.verify(signer.token(), "admin")
    fetch.failing = True
    clock.now += 301
    await verifier.verify(signer.token(), "admin")
    await verifier.verify(signer.token(), "admin")
    assert fetch.calls == 2  # a segunda requisição dentro do backoff não chamou o fetch
    clock.now += 31
    await verifier.verify(signer.token(), "admin")
    assert fetch.calls == 3  # passado o backoff, tenta de novo


async def test_failed_fetch_backoff_skips_fetch_with_empty_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock()
    monkeypatch.setattr("ks_platform.auth.time.monotonic", clock)
    signer = Signer()
    fetch = FlakyFetch({"keys": [signer.jwk]})
    fetch.failing = True
    verifier = TokenVerifier(JwksKeyProvider("http://identity/jwks", fetch=fetch))
    for _ in range(3):
        with pytest.raises(ProblemError) as exc:
            await verifier.verify(signer.token(), "admin")
        assert (exc.value.status, exc.value.code) == (503, "auth.jwks_unavailable")
    assert fetch.calls == 1
    fetch.failing = False
    clock.now += 31
    await verifier.verify(signer.token(), "admin")
    assert fetch.calls == 2


def _app(signer: Signer) -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)
    app.state.token_verifier = _verifier(FakeFetch({"keys": [signer.jwk]}))

    @app.get("/me")
    async def me(principal: Principal = Depends(require_audience("admin"))) -> dict[str, str]:  # noqa: B008
        return {"user_id": str(principal.user_id)}

    @app.post("/things")
    async def things(
        principal: Principal = Depends(require_permission("catalog.write")),  # noqa: B008
    ) -> dict[str, str]:
        return {"user_id": str(principal.user_id)}

    return app


async def _call(
    app: FastAPI, method: str, path: str, headers: dict[str, str] | None = None
) -> httpx.Response:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        return await client.request(method, path, headers=headers)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_missing_token_is_401_with_challenge() -> None:
    resp = await _call(_app(Signer()), "GET", "/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.missing_token"
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_non_bearer_scheme_is_missing_token() -> None:
    resp = await _call(_app(Signer()), "GET", "/me", {"Authorization": "Basic abc"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.missing_token"


async def test_invalid_token_is_401_with_challenge() -> None:
    resp = await _call(_app(Signer()), "GET", "/me", _bearer("garbage"))
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.invalid_token"
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_valid_token_passes_dependency() -> None:
    signer = Signer()
    resp = await _call(_app(signer), "GET", "/me", _bearer(signer.token()))
    assert resp.status_code == 200


async def test_wrong_audience_is_403_over_http() -> None:
    signer = Signer()
    token = signer.token(aud="storefront", kind="customer")
    resp = await _call(_app(signer), "GET", "/me", _bearer(token))
    assert resp.status_code == 403
    assert resp.json()["code"] == "auth.forbidden"


async def test_customer_role_lacks_permission() -> None:
    signer = Signer()
    resp = await _call(_app(signer), "POST", "/things", _bearer(signer.token(roles=[])))
    assert resp.status_code == 403
    assert resp.json()["code"] == "auth.forbidden"


async def test_admin_role_has_permission() -> None:
    signer = Signer()
    resp = await _call(_app(signer), "POST", "/things", _bearer(signer.token(roles=["admin"])))
    assert resp.status_code == 200
