import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from identity.adapters.models import RefreshToken, User
from identity.adapters.repositories import (
    SessionScope,
    SqlRefreshTokenRepository,
    SqlUserRepository,
)
from identity.application import auth_service as auth_module
from identity.application.auth_service import AuthError, AuthService, TokenPair
from identity.domain.lockout import LOCK_DURATION, MAX_FAILURES
from identity.domain.passwords import DUMMY_HASH
from identity.domain.tokens import SigningKey

PASSWORD = "Correto-Cavalo-Bateria-9"  # noqa: S105 (senha de teste)


class FakeClock:
    def __init__(self) -> None:
        self.start = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
        self.now = self.start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
async def session_factory(migrated_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE users CASCADE"))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def key() -> SigningKey:
    return SigningKey(kid="test-kid", private_key=Ed25519PrivateKey.generate())


@pytest.fixture
def service(
    session_factory: async_sessionmaker[AsyncSession], key: SigningKey, clock: FakeClock
) -> AuthService:
    scope = SessionScope(session_factory)
    return AuthService(SqlUserRepository(scope), SqlRefreshTokenRepository(scope), key, clock)


def _claims(key: SigningKey, token: str, audience: str) -> dict[str, object]:
    public = key.private_key.public_key()
    # o relógio do teste é fixo: valida assinatura e claims, não o tempo real
    return jwt.decode(
        token,
        public,
        algorithms=["EdDSA"],
        audience=audience,
        options={"verify_exp": False, "verify_iat": False},
    )


async def _expect(code: str, coro: object) -> AuthError:
    with pytest.raises(AuthError) as info:
        await coro  # type: ignore[misc]
    assert info.value.code == code
    return info.value


async def test_register_then_login_customer(
    service: AuthService, key: SigningKey, clock: FakeClock
) -> None:
    registered = await service.register("cliente@example.com", PASSWORD, "Cliente")
    logged = await service.login("cliente@example.com", PASSWORD, "storefront")

    for pair in (registered, logged):
        assert isinstance(pair, TokenPair)
        assert pair.expires_in == 900
        claims = _claims(key, pair.access_token, "storefront")
        assert claims["kind"] == "customer"
        assert claims["roles"] == []
    assert registered.refresh_token != logged.refresh_token
    assert logged.refresh_expires_at == clock.start + timedelta(days=30)


async def test_register_normalizes_email(
    service: AuthService, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await service.register("  Ana@X.com ", PASSWORD, "Ana")

    await service.login("ana@x.com", PASSWORD, "storefront")
    await _expect("identity.auth.email_taken", service.register("ana@x.com", PASSWORD, "Ana 2"))
    async with session_factory() as session:
        emails = (await session.scalars(select(User.email))).all()
    assert emails == ["ana@x.com"]


async def test_weak_password_rejected_with_codes(service: AuthService) -> None:
    error = await _expect(
        "identity.auth.weak_password", service.register("Joana@example.com", "xjoanax1", "Joana")
    )
    assert error.violations == ["too_short", "contains_email"]
    await _expect(
        "identity.auth.weak_password", service.register("ze@example.com", "password123", "Zé")
    )


async def test_customer_cannot_login_as_admin(service: AuthService) -> None:
    await service.register("cliente@example.com", PASSWORD, "Cliente")

    await _expect(
        "identity.auth.invalid_credentials",
        service.login("cliente@example.com", PASSWORD, "admin"),
    )


async def test_unknown_email_verifies_dummy_hash(
    service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    original = auth_module.verify_password

    def spy(hash: str, password: str) -> bool:  # noqa: A002
        seen.append(hash)
        return original(hash, password)

    monkeypatch.setattr(auth_module, "verify_password", spy)

    await _expect(
        "identity.auth.invalid_credentials",
        service.login("ninguem@example.com", PASSWORD, "storefront"),
    )
    assert seen == [DUMMY_HASH]


async def test_wrong_password_counts_and_locks(
    service: AuthService, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    await service.register("cliente@example.com", PASSWORD, "Cliente")
    for _ in range(MAX_FAILURES):
        await _expect(
            "identity.auth.invalid_credentials",
            service.login("cliente@example.com", "senha-errada-123", "storefront"),
        )

    # bloqueada: senha certa também falha, e o hash ainda é verificado (trabalho constante)
    seen: list[str] = []
    original = auth_module.verify_password

    def spy(hash: str, password: str) -> bool:  # noqa: A002
        seen.append(hash)
        return original(hash, password)

    monkeypatch.setattr(auth_module, "verify_password", spy)
    await _expect(
        "identity.auth.invalid_credentials",
        service.login("cliente@example.com", PASSWORD, "storefront"),
    )
    assert len(seen) == 1
    assert seen[0] != DUMMY_HASH

    clock.advance(LOCK_DURATION.total_seconds() + 1)
    await service.login("cliente@example.com", PASSWORD, "storefront")


async def test_successful_login_resets_failures(
    service: AuthService, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await service.register("cliente@example.com", PASSWORD, "Cliente")
    for _ in range(MAX_FAILURES - 1):
        await _expect(
            "identity.auth.invalid_credentials",
            service.login("cliente@example.com", "senha-errada-123", "storefront"),
        )
    async with session_factory() as session:
        assert await session.scalar(select(User.failed_logins)) == MAX_FAILURES - 1

    await service.login("cliente@example.com", PASSWORD, "storefront")

    async with session_factory() as session:
        assert await session.scalar(select(User.failed_logins)) == 0


async def test_refresh_rotates(service: AuthService, clock: FakeClock, key: SigningKey) -> None:
    first = await service.register("cliente@example.com", PASSWORD, "Cliente")

    clock.advance(60)
    second = await service.refresh(first.refresh_token)
    assert second.refresh_token != first.refresh_token
    assert _claims(key, second.access_token, "storefront")["kind"] == "customer"
    assert second.refresh_expires_at == clock.now + timedelta(days=30)

    third = await service.refresh(second.refresh_token)
    assert third.refresh_token not in {first.refresh_token, second.refresh_token}

    clock.advance(11)
    await _expect("identity.auth.refresh_reused", service.refresh(first.refresh_token))


async def test_refresh_reuse_within_grace_issues_new_pair(
    service: AuthService, clock: FakeClock
) -> None:
    pair = await service.register("cliente@example.com", PASSWORD, "Cliente")

    tab_a = await service.refresh(pair.refresh_token)
    clock.advance(5)
    tab_b = await service.refresh(pair.refresh_token)

    assert tab_a.refresh_token != tab_b.refresh_token
    # a família continua ativa: os dois sucessores seguem válidos
    await service.refresh(tab_a.refresh_token)
    await service.refresh(tab_b.refresh_token)


async def test_concurrent_refresh_of_same_token_both_succeed(service: AuthService) -> None:
    pair = await service.register("cliente@example.com", PASSWORD, "Cliente")

    tab_a, tab_b = await asyncio.gather(
        service.refresh(pair.refresh_token), service.refresh(pair.refresh_token)
    )

    assert tab_a.refresh_token != tab_b.refresh_token
    await service.refresh(tab_a.refresh_token)
    await service.refresh(tab_b.refresh_token)


async def test_refresh_reuse_after_grace_revokes_family(
    service: AuthService, clock: FakeClock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    pair = await service.register("cliente@example.com", PASSWORD, "Cliente")
    successor = await service.refresh(pair.refresh_token)

    clock.advance(11)
    await _expect("identity.auth.refresh_reused", service.refresh(pair.refresh_token))
    await _expect("identity.auth.invalid_refresh", service.refresh(successor.refresh_token))
    async with session_factory() as session:
        active = await session.scalar(
            select(func.count()).select_from(RefreshToken).where(RefreshToken.revoked_at.is_(None))
        )
    assert active == 0


async def test_refresh_unknown_or_expired_is_invalid(
    service: AuthService, clock: FakeClock
) -> None:
    await _expect("identity.auth.invalid_refresh", service.refresh("nao-existe"))

    pair = await service.register("cliente@example.com", PASSWORD, "Cliente")
    clock.advance(timedelta(days=30).total_seconds() + 1)
    await _expect("identity.auth.invalid_refresh", service.refresh(pair.refresh_token))


async def test_logout_revokes_family(service: AuthService) -> None:
    pair = await service.register("cliente@example.com", PASSWORD, "Cliente")
    successor = await service.refresh(pair.refresh_token)

    await service.logout(successor.refresh_token)

    await _expect("identity.auth.invalid_refresh", service.refresh(successor.refresh_token))
    await _expect("identity.auth.invalid_refresh", service.refresh(pair.refresh_token))
    # logout de token desconhecido ou já revogado não falha
    await service.logout(successor.refresh_token)
    await service.logout("nao-existe")


async def test_bootstrap_admin_idempotent(
    service: AuthService,
    key: SigningKey,
    clock: FakeClock,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await service.ensure_bootstrap_admin(" Admin@KatoShop.localhost ", PASSWORD)
    await service.ensure_bootstrap_admin("outro@katoshop.localhost", PASSWORD)

    async with session_factory() as session:
        staff = await session.scalar(
            select(func.count()).select_from(User).where(User.kind == "staff")
        )
    assert staff == 1

    pair = await service.login("admin@katoshop.localhost", PASSWORD, "admin")
    claims = _claims(key, pair.access_token, "admin")
    assert claims["kind"] == "staff"
    assert claims["roles"] == ["admin"]
    assert pair.refresh_expires_at == clock.start + timedelta(hours=12)
    await _expect(
        "identity.auth.invalid_credentials",
        service.login("admin@katoshop.localhost", PASSWORD, "storefront"),
    )
