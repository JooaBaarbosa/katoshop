"""Cursores opacos de paginação keyset: JSON compacto em base64url sem padding."""

import base64
import binascii
import json

from ks_platform.errors import ProblemError

INVALID_CURSOR = "catalog.pagination.invalid_cursor"
# Cursores legítimos ficam bem abaixo disso; o teto barra payloads enormes antes do parse.
MAX_CURSOR_LENGTH = 512


def invalid_cursor() -> ProblemError:
    return ProblemError(422, INVALID_CURSOR, "Cursor de paginação inválido")


def encode_cursor(payload: dict[str, str]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_cursor(raw: str, keys: tuple[str, ...]) -> dict[str, str]:
    """Devolve o payload se for um objeto com exatamente `keys`, todas com valor string.

    Qualquer desvio (tamanho, base64 ou JSON inválido, aninhamento profundo, outro tipo,
    outras chaves) vira 422.
    """
    if len(raw) > MAX_CURSOR_LENGTH:
        raise invalid_cursor()
    try:
        data: object = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (binascii.Error, ValueError, UnicodeDecodeError, RecursionError) as exc:
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
