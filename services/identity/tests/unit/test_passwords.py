import threading
import time
from concurrent.futures import ThreadPoolExecutor
from importlib import resources

import pytest

from identity.domain import passwords
from identity.domain.passwords import (
    DUMMY_HASH,
    hash_password,
    validate_password,
    verify_password,
)


def test_too_short() -> None:
    assert validate_password("curta", "a@b.com") == ["too_short"]


def test_too_common() -> None:
    assert validate_password("password123", "a@b.com") == ["too_common"]


def test_too_common_is_case_insensitive() -> None:
    assert validate_password("PassWord123", "a@b.com") == ["too_common"]


def test_contains_email_local_part() -> None:
    assert validate_password("joaosilva-forte-1", "joaosilva@x.com") == ["contains_email"]


def test_contains_email_is_case_insensitive() -> None:
    assert validate_password("JoaoSilva-forte-1", "joaosilva@x.com") == ["contains_email"]


def test_short_local_part_is_ignored() -> None:
    assert validate_password("abc-forte-senha-1", "abc@x.com") == []


def test_error_codes_come_in_fixed_order() -> None:
    assert validate_password("password", "password@x.com") == [
        "too_short",
        "too_common",
        "contains_email",
    ]


def test_valid_password() -> None:
    assert validate_password("s3nh4-longa!", "a@b.com") == []


def test_hash_roundtrip_uses_argon2id() -> None:
    hashed = hash_password("s3nh4-longa!")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "s3nh4-longa!") is True


def test_verify_rejects_wrong_password() -> None:
    assert verify_password(hash_password("s3nh4-longa!"), "outra-senha") is False


def test_verify_rejects_malformed_hash() -> None:
    assert verify_password("not-a-hash", "x") is False


def test_dummy_hash_is_valid_argon2id_and_rejects_everything() -> None:
    assert DUMMY_HASH.startswith("$argon2id$")
    assert verify_password(DUMMY_HASH, "qualquer") is False


def test_common_passwords_file_is_packaged_and_loaded() -> None:
    data = resources.files("identity.domain").joinpath("data/common-passwords.txt")
    assert data.is_file()
    assert "123456" in passwords.COMMON_PASSWORDS
    assert not any(line.startswith("#") for line in passwords.COMMON_PASSWORDS)


def test_argon2_concurrency_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    # cada hash Argon2 usa 64 MiB; sem limite, uma rajada de logins estoura o mem_limit
    in_flight = 0
    peak = 0
    lock = threading.Lock()

    class SlowHasher:
        def _work(self) -> None:
            nonlocal in_flight, peak
            with lock:
                in_flight += 1
                peak = max(peak, in_flight)
            time.sleep(0.02)
            with lock:
                in_flight -= 1

        def hash(self, password: str) -> str:
            self._work()
            return "h"

        def verify(self, hash: str, password: str) -> bool:  # noqa: A002
            self._work()
            return True

    monkeypatch.setattr(passwords, "_hasher", SlowHasher())
    with ThreadPoolExecutor(16) as pool:
        list(
            pool.map(
                lambda i: hash_password("x") if i % 2 else verify_password("h", "x"), range(32)
            )
        )

    assert peak == passwords.MAX_CONCURRENT_HASHES
