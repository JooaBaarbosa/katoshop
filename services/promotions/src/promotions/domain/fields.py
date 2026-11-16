"""Regras entre campos de um cupom, compartilhadas por criação e edição parcial."""

from datetime import datetime
from typing import Any

MAX_PERCENT = 90


def cross_field_errors(
    kind: str, value: int, starts_at: datetime | None, ends_at: datetime | None
) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    if kind == "percent" and not 1 <= value <= MAX_PERCENT:
        errors["body.value"] = [f"Percentual deve ficar entre 1 e {MAX_PERCENT}"]
    elif kind == "fixed" and value < 1:
        errors["body.value"] = ["Valor fixo deve ser de pelo menos 1 centavo"]
    if starts_at is not None and ends_at is not None and ends_at <= starts_at:
        errors["body.ends_at"] = ["Fim deve ser depois do início"]
    return errors


def merged_errors(current: Any, changes: dict[str, Any]) -> dict[str, list[str]]:
    """Valida o estado resultante de aplicar `changes` sobre `current` (objeto com atributos)."""

    def pick(name: str) -> Any:
        return changes[name] if name in changes else getattr(current, name)

    return cross_field_errors(pick("kind"), pick("value"), pick("starts_at"), pick("ends_at"))
