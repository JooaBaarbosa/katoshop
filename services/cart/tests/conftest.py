import base64
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cart.main import create_app
from cart.settings import CartSettings

pytest_plugins = ["ks_platform.testing"]


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
        roles: list[str] | None = None,
        expires_in: int = 900,
    ) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": "katoshop-identity",
            "aud": aud,
            "sub": str(sub),
            "iat": now,
            "exp": now + expires_in,
            "jti": str(uuid.uuid4()),
            "roles": roles or [],
            "kind": kind,
        }
        return jwt.encode(claims, self._private, algorithm="EdDSA", headers={"kid": self.kid})


@pytest.fixture(scope="session")
def signer() -> TestSigner:
    return TestSigner()


@pytest.fixture
async def client(
    redis_url: str,
    asgi_client_factory: Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]],
) -> AsyncIterator[httpx.AsyncClient]:
    async with asgi_client_factory(
        create_app(CartSettings(redis_url=redis_url, client_secret="test-secret"))  # noqa: S106
    ) as http_client:
        yield http_client
