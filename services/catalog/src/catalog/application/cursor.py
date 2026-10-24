"""Cursores opacos de paginação keyset: JSON compacto em base64url sem padding."""

import base64
import binascii
import json

from ks_platform.errors import ProblemError

INVALID_CURSOR = "catalog.pagination.invalid_cursor"


def invalid_cursor() -> ProblemError:
    return ProblemError(422, INVALID_CURSOR, "Cursor de paginação inválido")


def encode_cursor(payload: dict[str, str]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_cursor(raw: str, keys: tuple[str, ...]) -> dict[str, str]:
    """Devolve o payload se for um objeto com exatamente `keys`, todas com valor string.

    Qualquer desvio (base64 ou JSON inválido, outro tipo, outras chaves) vira 422.
    """
    try:
        data: object = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise invalid_cursor() from exc
    if not isinstance(data, dict) or set(data) != set(keys):  # pyright: ignore[reportUnknownArgumentType]
        raise invalid_cursor()
    payload: dict[str, str] = {}
    for key in keys:
        value: object = data[key]  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(value, str):
            raise invalid_cursor()
        payload[key] = value
    return payload
