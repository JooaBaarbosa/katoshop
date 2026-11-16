import base64
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from sqlalchemy import text

from ks_platform.auth import JwksKeyProvider, TokenVerifier
from promotions.main import create_app
from promotions.settings import PromotionsSettings

pytest_plugins = ["ks_platform.testing"]

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


class TestSigner:
    """Assina tokens no contrato do identity (EdDSA, iss, aud, kid) com uma chave de teste."""

    __test__ = False

    def __init__(self, kid: str = "test-key") -> None:
        self.kid = kid
        self._private = Ed25519PrivateKey.generate()

    @property
    def jwks(self) -> dict[str, Any]:
        raw = self._private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        x = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        jwk = {"kty": "OKP", "crv": "Ed25519", "x": x, "kid": self.kid, "alg": "EdDSA"}
        return {"keys": [jwk]}

    def token(
        self,
        *,
        sub: uuid.UUID | str,
        aud: str,
        kind: str,
        roles: list[str],
    ) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": "katoshop-identity",
            "aud": aud,
            "sub": str(sub),
            "iat": now,
            "exp": now + 900,
            "jti": str(uuid.uuid4()),
            "roles": roles,
            "kind": kind,
        }
        return jwt.encode(claims, self._private, algorithm="EdDSA", headers={"kid": self.kid})


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> str:
    from ks_platform.testing import run_migrations  # noqa: PLC0415

    run_migrations(ALEMBIC_INI, postgres_url)
    return postgres_url


@pytest.fixture(scope="session")
def signer() -> TestSigner:
    return TestSigner()


@pytest.fixture
def settings(migrated_url: str) -> PromotionsSettings:
    return PromotionsSettings(database_url=migrated_url)


@pytest.fixture
def app(settings: PromotionsSettings, signer: TestSigner) -> FastAPI:
    application = create_app(settings)

    async def fetch(_url: str) -> dict[str, Any]:
        return signer.jwks

    application.state.token_verifier = TokenVerifier(
        JwksKeyProvider("http://test/jwks", fetch=fetch)
    )
    return application


@pytest.fixture
async def client(
    app: FastAPI,
    asgi_client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> AsyncIterator[httpx.AsyncClient]:
    async with asgi_client_factory(app) as http_client:
        yield http_client


@pytest.fixture
def admin_token(signer: TestSigner) -> str:
    return signer.token(sub=uuid.uuid7(), aud="admin", kind="staff", roles=["admin"])


@pytest.fixture
def customer_token(signer: TestSigner) -> str:
    return signer.token(sub=uuid.uuid7(), aud="storefront", kind="customer", roles=[])


@pytest.fixture
def service_token(signer: TestSigner) -> str:
    return signer.token(sub="cart", aud="service", kind="service", roles=[])


@pytest.fixture
def staff_without_roles_token(signer: TestSigner) -> str:
    return signer.token(sub=uuid.uuid7(), aud="admin", kind="staff", roles=[])


def unique_code(prefix: str = "T") -> str:
    return f"{prefix}-{uuid.uuid7().hex[-12:]}".upper()


@pytest.fixture
def new_code() -> Callable[[str], str]:
    return unique_code


@pytest.fixture
def redeem(app: FastAPI) -> Callable[..., Awaitable[None]]:
    """Insere um resgate direto no banco (a gravação real chega na fatia 3)."""

    async def insert(coupon_id: str, customer_id: uuid.UUID | None = None) -> None:
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO coupon_redemptions (id, coupon_id, customer_id, order_id) "
                    "VALUES (:id, :c, :cu, :o)"
                ),
                {
                    "id": uuid.uuid4(),
                    "c": coupon_id,
                    "cu": customer_id or uuid.uuid4(),
                    "o": uuid.uuid4(),
                },
            )

    return insert


@pytest.fixture
def admin_client(client: httpx.AsyncClient, admin_token: str) -> httpx.AsyncClient:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    return client
