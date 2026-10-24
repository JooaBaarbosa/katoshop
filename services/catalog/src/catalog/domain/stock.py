from enum import StrEnum


class StockReason(StrEnum):
    INITIAL = "initial"
    ADJUSTMENT = "adjustment"
    DAMAGE = "damage"
    RETURN = "return"


MANUAL_REASONS = frozenset(StockReason)


class StockError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def apply_adjustment(on_hand: int, reserved: int, delta: int, reason: str) -> int:
    if reason not in MANUAL_REASONS:
        raise StockError("catalog.stock.invalid_reason")
    if delta == 0:
        raise StockError("catalog.stock.zero_delta")
    new_on_hand = on_hand + delta
    if new_on_hand < reserved:
        raise StockError("catalog.stock.would_go_negative")
    return new_on_hand


def available(on_hand: int, reserved: int) -> int:
    return max(on_hand - reserved, 0)


def effective_price(base_price_cents: int, variant_price_cents: int | None) -> int:
    return base_price_cents if variant_price_cents is None else variant_price_cents
