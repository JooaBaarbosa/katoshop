import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from identity.adapters.signing import SigningKey, load_signing_key
from identity.domain.tokens import issue_access_token, new_refresh_token
from ks_platform.auth import JwksKeyProvider, TokenVerifier


@pytest.fixture
def signing_key(tmp_path: Path) -> SigningKey:
    path = tmp_path / "key.pem"
    path.write_bytes(
        Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return load_signing_key(path)


async def test_access_token_verifies_with_platform_verifier(signing_key: SigningKey) -> None:
    user_id = uuid.uuid4()
    token = issue_access_token(signing_key, user_id, "admin", "staff", ["admin"], datetime.now(UTC))

    async def fetch(_url: str) -> dict[str, Any]:
        return {"keys": [signing_key.public_jwk()]}

    verifier = TokenVerifier(JwksKeyProvider("http://jwks", fetch=fetch))
    principal = await verifier.verify(token, "admin")

    assert principal.user_id == user_id
    assert principal.kind == "staff"
    assert principal.roles == {"admin"}


def test_access_token_expires_in_900s(signing_key: SigningKey) -> None:
    token = issue_access_token(
        signing_key, uuid.uuid4(), "storefront", "customer", [], datetime.now(UTC)
    )
    claims = jwt.decode(token, options={"verify_signature": False})
    header = jwt.get_unverified_header(token)

    assert claims["exp"] - claims["iat"] == 900
    assert claims["iss"] == "katoshop-identity"
    assert claims["jti"]
    assert header["kid"] == signing_key.kid
    assert header["alg"] == "EdDSA"


def test_refresh_token_hash_matches() -> None:
    raw, digest = new_refresh_token()
    other_raw, other_digest = new_refresh_token()

    assert hashlib.sha256(raw.encode()).hexdigest() == digest
    assert raw != other_raw
    assert digest != other_digest


def test_kid_is_16_hex_of_public_key_sha256(signing_key: SigningKey) -> None:
    raw = signing_key.private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    assert signing_key.kid == hashlib.sha256(raw).hexdigest()[:16]
    jwk = signing_key.public_jwk()
    assert jwk["kty"] == "OKP"
    assert jwk["crv"] == "Ed25519"
    assert jwk["alg"] == "EdDSA"
    assert jwk["use"] == "sig"
    assert "=" not in jwk["x"]
    assert "d" not in jwk


def test_issue_access_token_rejects_naive_now(signing_key: SigningKey) -> None:
    with pytest.raises(ValueError, match="timezone"):
        issue_access_token(signing_key, uuid.uuid4(), "storefront", "customer", [], datetime.now())  # noqa: DTZ005


@pytest.mark.parametrize(
    ("audience", "kind"),
    [("backoffice", "staff"), ("admin", "robot"), ("", "customer")],
)
def test_issue_access_token_rejects_unknown_audience_or_kind(
    signing_key: SigningKey, audience: str, kind: str
) -> None:
    with pytest.raises(ValueError, match="audience|kind"):
        issue_access_token(
            signing_key,
            uuid.uuid4(),
            audience,  # pyright: ignore[reportArgumentType]
            kind,  # pyright: ignore[reportArgumentType]
            [],
            datetime.now(UTC),
        )
