import uuid
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from contextvars import ContextVar
from datetime import datetime

from sqlalchemy import exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.adapters.models import RefreshToken, Role, User, UserRole
from identity.application.ports import RefreshTokenRecord, UserRecord
from identity.domain.lockout import LoginState


class SessionScope:
    """Sessão compartilhada pelos repositórios dentro de uma transação.

    `transaction()` abre sessão + BEGIN e publica a sessão num ContextVar; repositórios que
    compartilham o mesmo escopo enxergam a mesma transação. Chamadas aninhadas reaproveitam
    a transação corrente. O ContextVar isola tarefas asyncio concorrentes.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory
        self._current: ContextVar[AsyncSession | None] = ContextVar(
            f"identity_session_{id(self)}", default=None
        )

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        if self._current.get() is not None:
            yield
            return
        async with self._factory() as session, session.begin():
            token = self._current.set(session)
            try:
                yield
            finally:
                self._current.reset(token)

    @property
    def session(self) -> AsyncSession:
        session = self._current.get()
        if session is None:
            raise RuntimeError("repositório usado fora de SessionScope.transaction()")
        return session


class SqlUserRepository:
    def __init__(self, scope: SessionScope) -> None:
        self._scope = scope

    def transaction(self) -> AbstractAsyncContextManager[None]:
        return self._scope.transaction()

    async def _record(self, user: User) -> UserRecord:
        roles = await self._scope.session.scalars(
            select(Role.key)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
            .order_by(Role.key)
        )
        return UserRecord(
            id=user.id,
            email=user.email,
            password_hash=user.password_hash,
            kind=user.kind,
            status=user.status,
            login_state=LoginState(user.failed_logins, user.locked_until),
            roles=list(roles),
        )

    async def get_by_email(self, email: str, *, for_update: bool = False) -> UserRecord | None:
        stmt = select(User).where(func.lower(User.email) == email.lower())
        if for_update:
            stmt = stmt.with_for_update()
        user = await self._scope.session.scalar(stmt)
        return None if user is None else await self._record(user)

    async def get_by_id(self, user_id: uuid.UUID) -> UserRecord | None:
        user = await self._scope.session.get(User, user_id)
        return None if user is None else await self._record(user)

    async def add(self, email: str, password_hash: str, name: str, kind: str) -> UserRecord | None:
        user_id = await self._scope.session.scalar(
            insert(User)
            .values(id=uuid.uuid7(), email=email, password_hash=password_hash, name=name, kind=kind)
            .on_conflict_do_nothing(index_elements=[func.lower(User.email)])
            .returning(User.id)
        )
        return None if user_id is None else await self.get_by_id(user_id)

    async def save_login_state(self, user_id: uuid.UUID, state: LoginState) -> None:
        await self._scope.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(failed_logins=state.failed_logins, locked_until=state.locked_until)
        )

    async def grant_role(self, user_id: uuid.UUID, role_key: str) -> None:
        role_id = select(Role.id).where(Role.key == role_key).scalar_subquery()
        await self._scope.session.execute(
            insert(UserRole).values(user_id=user_id, role_id=role_id).on_conflict_do_nothing()
        )

    async def any_staff(self) -> bool:
        return bool(await self._scope.session.scalar(select(exists().where(User.kind == "staff"))))


class SqlRefreshTokenRepository:
    def __init__(self, scope: SessionScope) -> None:
        self._scope = scope

    def transaction(self) -> AbstractAsyncContextManager[None]:
        return self._scope.transaction()

    @staticmethod
    def _record(row: RefreshToken) -> RefreshTokenRecord:
        return RefreshTokenRecord(
            id=row.id,
            user_id=row.user_id,
            family_id=row.family_id,
            audience=row.audience,
            expires_at=row.expires_at,
            first_used_at=row.first_used_at,
            revoked_at=row.revoked_at,
            replaced_by=row.replaced_by,
        )

    async def add(
        self,
        *,
        user_id: uuid.UUID,
        family_id: uuid.UUID,
        token_hash: str,
        audience: str,
        expires_at: datetime,
    ) -> uuid.UUID:
        token_id = uuid.uuid7()
        await self._scope.session.execute(
            insert(RefreshToken).values(
                id=token_id,
                user_id=user_id,
                family_id=family_id,
                token_hash=token_hash,
                audience=audience,
                expires_at=expires_at,
            )
        )
        return token_id

    async def _get(self, token_hash: str, *, for_update: bool) -> RefreshTokenRecord | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        if for_update:
            # populate_existing: relê a linha após esperar o lock, sem cache da identity map
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        row = await self._scope.session.scalar(stmt)
        return None if row is None else self._record(row)

    async def get_by_hash_for_update(self, token_hash: str) -> RefreshTokenRecord | None:
        return await self._get(token_hash, for_update=True)

    async def get_by_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        return await self._get(token_hash, for_update=False)

    async def family_revoked(self, family_id: uuid.UUID) -> bool:
        return bool(
            await self._scope.session.scalar(
                select(
                    exists().where(
                        RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_not(None)
                    )
                )
            )
        )

    async def mark_rotated(
        self, token_id: uuid.UUID, used_at: datetime, successor: uuid.UUID
    ) -> None:
        await self._scope.session.execute(
            update(RefreshToken)
            .where(RefreshToken.id == token_id)
            .values(first_used_at=used_at, replaced_by=successor)
        )

    async def revoke_family(self, family_id: uuid.UUID, now: datetime) -> None:
        await self._scope.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
