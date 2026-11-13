"""Envelope de eventos de domínio (spec geral §3.3)."""

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self

_VERSION_SUFFIX = re.compile(r"\.v([1-9][0-9]*)$")


def _str(body: dict[str, Any], key: str, *, optional: bool = False) -> str | None:
    value = body[key]
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"campo {key} inválido")
    return value


@dataclass(frozen=True)
class Envelope:
    id: uuid.UUID
    type: str
    version: int
    occurred_at: datetime
    correlation_id: str | None
    causation_id: str | None
    producer: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "type": self.type,
            "version": self.version,
            "occurred_at": self.occurred_at.isoformat(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "producer": self.producer,
            "data": self.data,
        }

    def to_json(self) -> bytes:
        return json.dumps(self.to_dict(), separators=(",", ":")).encode()

    @classmethod
    def from_dict(cls, body: object) -> Self:
        """Valida e constrói o envelope; levanta `ValueError` se faltar campo ou tipo errado."""
        if not isinstance(body, dict):
            raise ValueError("envelope deve ser um objeto JSON")
        try:
            version = body["version"]
            if isinstance(version, bool) or not isinstance(version, int) or version < 1:
                raise ValueError("campo version inválido")
            data = body["data"]
            if not isinstance(data, dict):
                raise ValueError("campo data inválido")
            occurred_at = datetime.fromisoformat(str(_str(body, "occurred_at")))
            if occurred_at.tzinfo is None:
                raise ValueError("campo occurred_at sem fuso horário")
            return cls(
                id=uuid.UUID(str(_str(body, "id"))),
                type=str(_str(body, "type")),
                version=version,
                occurred_at=occurred_at,
                correlation_id=_str(body, "correlation_id", optional=True),
                causation_id=_str(body, "causation_id", optional=True),
                producer=str(_str(body, "producer")),
                data=data,
            )
        except KeyError as exc:
            raise ValueError(f"campo ausente: {exc.args[0]}") from exc

    @classmethod
    def from_json(cls, raw: bytes) -> Self:
        try:
            body = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("JSON inválido") from exc
        return cls.from_dict(body)


def new_event(
    type: str,  # noqa: A002 - nome do campo do envelope
    producer: str,
    data: dict[str, Any],
    *,
    correlation_id: str | None = None,
) -> Envelope:
    """Cria o envelope com id UUIDv7; a versão vem do sufixo `.vN` do tipo."""
    match = _VERSION_SUFFIX.search(type)
    if match is None:
        raise ValueError(f"tipo de evento sem sufixo de versão .vN: {type!r}")
    return Envelope(
        id=uuid.uuid7(),
        type=type,
        version=int(match.group(1)),
        occurred_at=datetime.now(UTC),
        correlation_id=correlation_id,
        causation_id=None,
        producer=producer,
        data=data,
    )
