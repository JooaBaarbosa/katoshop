import uuid
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from identity.domain.lockout import LoginState


@dataclass(frozen=True)
class UserRecord:
    id: uuid.UUID
    email: str
    name: str
    password_hash: str
    kind: str
    status: str
    login_state: LoginState
    roles: list[str]


@dataclass(frozen=True)
class RefreshTokenRecord:
    id: uuid.UUID
    user_id: uuid.UUID
    family_id: uuid.UUID
    audience: str
    expires_at: datetime
    first_used_at: datetime | None
    revoked_at: datetime | None
    replaced_by: uuid.UUID | None


class Transactional(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[None]:
        """Abre uma transação; chamadas aninhadas reaproveitam a transação corrente."""
        ...


class UserRepository(Transactional, Protocol):
    async def get_by_email(self, email: str, *, for_update: bool = False) -> UserRecord | None: ...

    async def get_by_id(self, user_id: uuid.UUID) -> UserRecord | None: ...

    async def add(self, email: str, password_hash: str, name: str, kind: str) -> UserRecord | None:
        """Insere o usuário; devolve None se o email (case-insensitive) já existe."""
        ...

    async def update_profile(
        self,
        user_id: uuid.UUID,
        *,
        name: str | None = None,
        email: str | None = None,
        password_hash: str | None = None,
    ) -> bool:
        """Atualiza só os campos informados; devolve False se o novo email já existe."""
        ...

    async def save_login_state(self, user_id: uuid.UUID, state: LoginState) -> None: ...

    async def grant_role(self, user_id: uuid.UUID, role_key: str) -> None: ...

    async def any_staff(self) -> bool: ...


class RefreshTokenRepository(Transactional, Protocol):
    async def add(
        self,
        *,
        user_id: uuid.UUID,
        family_id: uuid.UUID,
        token_hash: str,
        audience: str,
        expires_at: datetime,
    ) -> uuid.UUID: ...

    async def get_by_hash_for_update(self, token_hash: str) -> RefreshTokenRecord | None: ...

    async def get_by_hash(self, token_hash: str) -> RefreshTokenRecord | None: ...

    async def family_revoked(self, family_id: uuid.UUID) -> bool: ...

    async def mark_rotated(
        self, token_id: uuid.UUID, used_at: datetime, successor: uuid.UUID
    ) -> None:
        """Primeiro uso: grava first_used_at e replaced_by."""
        ...

    async def revoke_family(self, family_id: uuid.UUID, now: datetime) -> None: ...
