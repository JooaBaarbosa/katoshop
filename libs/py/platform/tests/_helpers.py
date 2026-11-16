"""Helpers compartilhados pelos testes de auth."""

import base64
import time
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


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
