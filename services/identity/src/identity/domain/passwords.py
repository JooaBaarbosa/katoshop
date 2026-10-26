import threading
from importlib import resources

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_LENGTH = 10
MIN_EMAIL_LOCAL_LENGTH = 4


def _load_common_passwords() -> frozenset[str]:
    path = resources.files("identity.domain").joinpath("data/common-passwords.txt")
    lines = (line.strip() for line in path.read_text("utf-8").splitlines())
    return frozenset(line.lower() for line in lines if line and not line.startswith("#"))


COMMON_PASSWORDS = _load_common_passwords()
_hasher = PasswordHasher()
# Cada hash/verificação Argon2 aloca memory_cost (64 MiB por padrão). O pool do to_thread tem
# até cpu+4 threads, então uma rajada de logins estourava o mem_limit do container (OOM).
MAX_CONCURRENT_HASHES = 2
_hash_slots = threading.BoundedSemaphore(MAX_CONCURRENT_HASHES)


def validate_password(password: str, email: str) -> list[str]:
    errors: list[str] = []
    if len(password) < MIN_LENGTH:
        errors.append("too_short")
    if password.lower() in COMMON_PASSWORDS:
        errors.append("too_common")
    local_part = email.split("@", 1)[0].lower()
    if len(local_part) >= MIN_EMAIL_LOCAL_LENGTH and local_part in password.lower():
        errors.append("contains_email")
    return errors


def hash_password(password: str) -> str:
    with _hash_slots:
        return _hasher.hash(password)


def verify_password(hash: str, password: str) -> bool:  # noqa: A002
    with _hash_slots:
        try:
            return _hasher.verify(hash, password)
        except VerificationError, InvalidHashError:
            return False


DUMMY_HASH = hash_password("dummy-password-for-timing-equalization")
