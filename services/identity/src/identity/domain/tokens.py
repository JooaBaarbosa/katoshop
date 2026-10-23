import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, get_args

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ISSUER = "katoshop-identity"
ACCESS_TTL = timedelta(seconds=900)
REFRESH_TTL = {"storefront": timedelta(days=30), "admin": timedelta(hours=12)}
REUSE_GRACE = timedelta(seconds=10)

type Audience = Literal["storefront", "admin"]
type Kind = Literal["customer", "staff"]
AUDIENCES: frozenset[str] = frozenset(get_args(Audience.__value__))
KINDS: frozenset[str] = frozenset(get_args(Kind.__value__))


@dataclass(frozen=True)
class SigningKey:
    kid: str
    private_key: Ed25519PrivateKey

    def public_jwk(self) -> dict[str, str]:
        raw = self.private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return {
            "kty": "OKP",
            "crv": "Ed25519",
            "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii"),
            "kid": self.kid,
            "alg": "EdDSA",
            "use": "sig",
        }


def issue_access_token(
    key: SigningKey,
    user_id: uuid.UUID,
    audience: Audience,
    kind: Kind,
    roles: list[str],
    now: datetime,
) -> str:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now precisa ter timezone (naive datetime recusado)")
    if audience not in AUDIENCES:
        raise ValueError(f"audience desconhecida: {audience!r}")
    if kind not in KINDS:
        raise ValueError(f"kind desconhecido: {kind!r}")
    issued_at = now.astimezone(UTC)
    claims = {
        "iss": ISSUER,
        "sub": str(user_id),
        "aud": audience,
        "iat": issued_at,
        "exp": issued_at + ACCESS_TTL,
        "jti": str(uuid.uuid4()),
        "roles": roles,
        "kind": kind,
    }
    return jwt.encode(claims, key.private_key, algorithm="EdDSA", headers={"kid": key.kid})


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()
