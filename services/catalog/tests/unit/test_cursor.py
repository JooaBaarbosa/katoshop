import base64

import pytest

from catalog.application import cursor
from catalog.application.cursor import MAX_CURSOR_LENGTH, decode_cursor, encode_cursor
from ks_platform.errors import ProblemError


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _assert_invalid(raw: str) -> None:
    with pytest.raises(ProblemError) as raised:
        decode_cursor(raw, ("a",))
    assert (raised.value.status, raised.value.code) == (422, "catalog.pagination.invalid_cursor")


def test_round_trip() -> None:
    token = encode_cursor({"a": "1"})
    assert decode_cursor(token, ("a",)) == {"a": "1"}


def test_rejects_cursor_longer_than_limit() -> None:
    assert MAX_CURSOR_LENGTH == 512
    padded = encode_cursor({"a": "x" * 400})
    assert len(padded) > MAX_CURSOR_LENGTH
    _assert_invalid(padded)
    _assert_invalid("a" * 513)


def test_deeply_nested_json_is_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    # O limite de tamanho já barra isso; o RecursionError é tratado mesmo assim.
    monkeypatch.setattr(cursor, "MAX_CURSOR_LENGTH", 10**7)
    depth = 200_000
    _assert_invalid(_b64(b"[" * depth + b"]" * depth))
    _assert_invalid(_b64(b"[" * 10_000))


def test_non_ascii_is_invalid() -> None:
    _assert_invalid("não-ascii")
