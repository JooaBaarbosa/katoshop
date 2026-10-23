import hashlib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from identity.domain.tokens import SigningKey

__all__ = ["SigningKey", "load_signing_key"]


def load_signing_key(path: Path) -> SigningKey:
    private_key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError(f"{path} não contém uma chave privada Ed25519")
    raw_public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return SigningKey(kid=hashlib.sha256(raw_public).hexdigest()[:16], private_key=private_key)
