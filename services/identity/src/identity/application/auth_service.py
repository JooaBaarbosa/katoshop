import asyncio
import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from identity.application.ports import RefreshTokenRepository, UserRecord, UserRepository
from identity.domain.lockout import is_locked, register_failure, register_success
from identity.domain.passwords import DUMMY_HASH, hash_password, validate_password, verify_password
from identity.domain.tokens import (
    ACCESS_TTL,
    REFRESH_TTL,
    REUSE_GRACE,
    Audience,
    Kind,
    SigningKey,
    issue_access_token,
    new_refresh_token,
)

INVALID_CREDENTIALS = "identity.auth.invalid_credentials"
EMAIL_TAKEN = "identity.auth.email_taken"
WEAK_PASSWORD = "identity.auth.weak_password"  # noqa: S105 (código de erro, não senha)
INVALID_REFRESH = "identity.auth.invalid_refresh"
REFRESH_REUSED = "identity.auth.refresh_reused"
CURRENT_PASSWORD_REQUIRED = "identity.me.current_password_required"  # noqa: S105

_KIND_FOR_AUDIENCE: dict[str, Kind] = {"storefront": "customer", "admin": "staff"}


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_at: datetime
    user: UserRecord


class AuthError(Exception):
    def __init__(self, code: str, violations: list[str] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.violations: list[str] = violations or []


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_refresh(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class AuthService:
    """Casos de uso de autenticação.

    Cada método público roda numa única transação aberta via `users.transaction()` (os
    repositórios compartilham o escopo de sessão). Erros que precisam persistir estado
    (falha de login, revogação por reuso) são levantados depois do commit.
    """

    def __init__(
        self,
        users: UserRepository,
        tokens: RefreshTokenRepository,
        key: SigningKey,
        clock: Callable[[], datetime],
    ) -> None:
        self._users = users
        self._tokens = tokens
        self._key = key
        self._clock = clock

    async def register(self, email: str, password: str, name: str) -> TokenPair:
        email = _normalize_email(email)
        violations = validate_password(password, email)
        if violations:
            raise AuthError(WEAK_PASSWORD, violations)
        password_hash = await asyncio.to_thread(hash_password, password)
        async with self._users.transaction():
            user = await self._users.add(email, password_hash, name, "customer")
            if user is None:
                raise AuthError(EMAIL_TAKEN)
            return await self._issue(user, "storefront", uuid.uuid7())

    async def login(
        self, email: str, password: str, audience: Literal["storefront", "admin"]
    ) -> TokenPair:
        email = _normalize_email(email)
        async with self._users.transaction():
            now = self._clock()
            user = await self._users.get_by_email(email, for_update=True)
            if user is None:
                await asyncio.to_thread(verify_password, DUMMY_HASH, password)
                pair = None
            else:
                pair = await self._login_existing(user, password, audience, now)
        if pair is None:
            raise AuthError(INVALID_CREDENTIALS)
        return pair

    async def _login_existing(
        self, user: UserRecord, password: str, audience: Audience, now: datetime
    ) -> TokenPair | None:
        # verifica sempre o hash, mesmo bloqueada: tempo de resposta igual em todos os casos
        password_ok = await asyncio.to_thread(verify_password, user.password_hash, password)
        if is_locked(user.login_state, now):
            return None
        if not password_ok:
            await self._users.save_login_state(user.id, register_failure(user.login_state, now))
            return None
        if user.status != "active" or user.kind != _KIND_FOR_AUDIENCE[audience]:
            return None
        if user.login_state != register_success(user.login_state):
            await self._users.save_login_state(user.id, register_success(user.login_state))
        return await self._issue(user, audience, uuid.uuid7())

    async def refresh(self, raw: str) -> TokenPair:
        async with self._tokens.transaction():
            now = self._clock()
            result = await self._rotate(raw, now)
        if isinstance(result, AuthError):
            raise result
        return result

    async def _rotate(self, raw: str, now: datetime) -> TokenPair | AuthError:
        token = await self._tokens.get_by_hash_for_update(_hash_refresh(raw))
        if (
            token is None
            or now >= token.expires_at
            or await self._tokens.family_revoked(token.family_id)
        ):
            return AuthError(INVALID_REFRESH)
        user = await self._users.get_by_id(token.user_id)
        audience = cast(Audience, token.audience)
        if user is None or user.status != "active" or user.kind != _KIND_FOR_AUDIENCE[audience]:
            return AuthError(INVALID_REFRESH)

        if token.replaced_by is None and token.revoked_at is None:
            pair, successor = await self._issue_with_id(user, audience, token.family_id)
            await self._tokens.mark_rotated(token.id, now, successor)
            return pair
        if token.first_used_at is not None and now - token.first_used_at <= REUSE_GRACE:
            # corrida de abas: outro sucessor na mesma família, sem revogar
            return await self._issue(user, audience, token.family_id)
        await self._tokens.revoke_family(token.family_id, now)
        return AuthError(REFRESH_REUSED)

    async def logout(self, raw: str) -> None:
        async with self._tokens.transaction():
            token = await self._tokens.get_by_hash(_hash_refresh(raw))
            if token is not None:
                await self._tokens.revoke_family(token.family_id, self._clock())

    async def get_user(self, user_id: uuid.UUID) -> UserRecord | None:
        async with self._users.transaction():
            return await self._users.get_by_id(user_id)

    async def update_profile(
        self,
        user_id: uuid.UUID,
        *,
        name: str | None = None,
        email: str | None = None,
        new_password: str | None = None,
        current_password: str | None = None,
    ) -> UserRecord:
        email = None if email is None else _normalize_email(email)
        async with self._users.transaction():
            user = await self._users.get_by_id(user_id)
            if user is None or user.status != "active":
                raise AuthError(INVALID_CREDENTIALS)
            new_hash: str | None = None
            changes_credentials = new_password is not None or (
                email is not None and email != user.email
            )
            if changes_credentials:
                if not current_password:
                    raise AuthError(CURRENT_PASSWORD_REQUIRED)
                if not await asyncio.to_thread(
                    verify_password, user.password_hash, current_password
                ):
                    raise AuthError(INVALID_CREDENTIALS)
            if new_password is not None:
                violations = validate_password(new_password, email or user.email)
                if violations:
                    raise AuthError(WEAK_PASSWORD, violations)
                new_hash = await asyncio.to_thread(hash_password, new_password)
            if not await self._users.update_profile(
                user_id, name=name, email=email, password_hash=new_hash
            ):
                raise AuthError(EMAIL_TAKEN)
            updated = await self._users.get_by_id(user_id)
            assert updated is not None  # noqa: S101
            return updated

    async def create_staff(self, email: str, password: str, name: str, role: str = "admin") -> None:
        email = _normalize_email(email)
        violations = validate_password(password, email)
        if violations:
            raise AuthError(WEAK_PASSWORD, violations)
        password_hash = await asyncio.to_thread(hash_password, password)
        async with self._users.transaction():
            user = await self._users.add(email, password_hash, name, "staff")
            if user is None:
                raise AuthError(EMAIL_TAKEN)
            await self._users.grant_role(user.id, role)

    async def ensure_bootstrap_admin(self, email: str, password: str) -> None:
        email = _normalize_email(email)
        async with self._users.transaction():
            if await self._users.any_staff():
                return
            password_hash = await asyncio.to_thread(hash_password, password)
            user = await self._users.add(email, password_hash, "Administrador", "staff")
            if user is None:
                # outra instância pode ter criado o mesmo admin em paralelo: aí está tudo certo
                if await self._users.any_staff():
                    return
                raise RuntimeError("bootstrap admin email already in use by a non-staff user")
            await self._users.grant_role(user.id, "admin")

    async def _issue(self, user: UserRecord, audience: Audience, family_id: uuid.UUID) -> TokenPair:
        pair, _ = await self._issue_with_id(user, audience, family_id)
        return pair

    async def _issue_with_id(
        self, user: UserRecord, audience: Audience, family_id: uuid.UUID
    ) -> tuple[TokenPair, uuid.UUID]:
        now = self._clock()
        access = issue_access_token(
            self._key, user.id, audience, cast(Kind, user.kind), user.roles, now
        )
        raw, token_hash = new_refresh_token()
        expires_at = now + REFRESH_TTL[audience]
        token_id = await self._tokens.add(
            user_id=user.id,
            family_id=family_id,
            token_hash=token_hash,
            audience=audience,
            expires_at=expires_at,
        )
        pair = TokenPair(
            access_token=access,
            refresh_token=raw,
            expires_in=int(ACCESS_TTL.total_seconds()),
            refresh_expires_at=expires_at,
            user=user,
        )
        return pair, token_id
