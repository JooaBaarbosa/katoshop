import pytest

from catalog.domain.stock import (
    MANUAL_REASONS,
    StockError,
    StockReason,
    apply_adjustment,
    available,
    effective_price,
)


def _code(exc: pytest.ExceptionInfo[StockError]) -> str:
    return exc.value.code


def test_negative_result_below_reserved_fails():
    with pytest.raises(StockError) as e:
        apply_adjustment(5, 0, -6, "adjustment")
    assert _code(e) == "catalog.stock.would_go_negative"


def test_cannot_drop_below_reserved():
    with pytest.raises(StockError) as e:
        apply_adjustment(5, 3, -3, "damage")
    assert _code(e) == "catalog.stock.would_go_negative"


def test_adjustment_down_to_reserved_ok():
    assert apply_adjustment(5, 2, -3, "damage") == 2


def test_zero_delta_fails():
    with pytest.raises(StockError) as e:
        apply_adjustment(5, 0, 0, "adjustment")
    assert _code(e) == "catalog.stock.zero_delta"


def test_invalid_reason_fails():
    with pytest.raises(StockError) as e:
        apply_adjustment(5, 0, 1, "sale")
    assert _code(e) == "catalog.stock.invalid_reason"


def test_reasons():
    assert {r.value for r in MANUAL_REASONS} == {"initial", "adjustment", "damage", "return"}
    assert StockReason.RETURN == "return"


def test_available_never_negative():
    assert available(5, 2) == 3
    assert available(1, 4) == 0


def test_effective_price():
    assert effective_price(10000, None) == 10000
    assert effective_price(10000, 12900) == 12900
    assert effective_price(10000, 0) == 0
