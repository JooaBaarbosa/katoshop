from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from promotions.domain.coupons import (
    CouponRule,
    LineItem,
    allocate,
    evaluate,
    normalize_code,
)

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def rule(**over: object) -> CouponRule:
    base = CouponRule(
        code="BEMVINDO10",
        kind="percent",
        value=10,
        min_order_cents=None,
        starts_at=None,
        ends_at=None,
        category_slugs=frozenset(),
        collection_slugs=frozenset(),
        max_uses_total=None,
        max_uses_per_customer=None,
        active=True,
    )
    return replace(base, **over)  # type: ignore[arg-type]


def item(
    variant_id: str = "v1",
    price: int = 29900,
    qty: int = 1,
    cat: str = "camisetas",
    cols: frozenset[str] = frozenset(),
) -> LineItem:
    return LineItem(variant_id, price, qty, cat, cols)


def ev(
    r: CouponRule,
    items: list[LineItem] | None = None,
    *,
    customer_id: str | None = "c1",
    uses_total: int = 0,
    uses_by_customer: int = 0,
    now: datetime = NOW,
):
    return evaluate(
        r,
        items or [item()],
        now=now,
        customer_id=customer_id,
        uses_total=uses_total,
        uses_by_customer=uses_by_customer,
    )


def test_normalize_code_strip_upper() -> None:
    assert normalize_code(" bemvindo10 ") == "BEMVINDO10"


@pytest.mark.parametrize("raw", ["ab", "a b c", "abc$", "x" * 33, ""])
def test_normalize_code_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_code(raw)


def test_percent_discount() -> None:
    r = ev(rule())
    assert r.valid and r.discount_cents == 2990 and r.per_item == {"v1": 2990}
    assert r.reason is None


def test_fixed_capped_by_eligible_total() -> None:
    r = ev(rule(kind="fixed", value=5000), [item(price=3000)])
    assert r.valid and r.discount_cents == 3000


def test_inactive_and_expired_returns_inactive() -> None:
    r = ev(rule(active=False, ends_at=NOW - timedelta(days=1)))
    assert not r.valid and r.reason == "promotions.coupon.inactive"
    assert r.discount_cents == 0 and r.per_item == {}


def test_not_started() -> None:
    r = ev(rule(starts_at=NOW + timedelta(seconds=1)))
    assert r.reason == "promotions.coupon.not_started"


def test_starts_at_inclusive() -> None:
    assert ev(rule(starts_at=NOW)).valid


def test_ends_at_exclusive() -> None:
    assert ev(rule(ends_at=NOW)).reason == "promotions.coupon.expired"
    assert ev(rule(ends_at=NOW + timedelta(seconds=1))).valid


def test_naive_now_rejected() -> None:
    with pytest.raises(ValueError):
        ev(rule(), now=datetime(2026, 11, 16, 12, 0))


def test_empty_items_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate(rule(), [], now=NOW, customer_id=None, uses_total=0, uses_by_customer=0)


def test_collection_restriction_only_eligible_item_discounted() -> None:
    r = rule(collection_slugs=frozenset({"verao"}))
    items = [item("v1", 10000, 1, cols=frozenset({"verao"})), item("v2", 20000, 1)]
    out = ev(r, items)
    assert out.valid and out.discount_cents == 1000 and out.per_item == {"v1": 1000}


def test_category_restriction() -> None:
    r = rule(category_slugs=frozenset({"calcas"}))
    out = ev(r, [item("v1", cat="camisetas"), item("v2", 10000, cat="calcas")])
    assert out.per_item == {"v2": 1000}


def test_no_eligible_items() -> None:
    r = rule(category_slugs=frozenset({"calcas"}))
    assert ev(r).reason == "promotions.coupon.no_eligible_items"


def test_min_order_not_met_uses_eligible_sum_and_returns_minimum() -> None:
    r = rule(min_order_cents=50000, collection_slugs=frozenset({"verao"}))
    items = [item("v1", 20000, 2, cols=frozenset({"verao"})), item("v2", 90000)]
    out = ev(r, items)
    assert out.reason == "promotions.coupon.min_order_not_met"
    assert out.min_order_cents == 50000 and out.discount_cents == 0


def test_min_order_met_exactly() -> None:
    assert ev(rule(min_order_cents=29900)).valid


def test_usage_limit_reached() -> None:
    r = rule(max_uses_total=5)
    assert ev(r, uses_total=5).reason == "promotions.coupon.usage_limit_reached"
    assert ev(r, uses_total=4).valid


def test_visitor_needs_login_when_per_customer_limit() -> None:
    r = rule(max_uses_per_customer=1)
    assert ev(r, customer_id=None).reason == "promotions.coupon.login_required"


def test_visitor_ok_without_per_customer_limit() -> None:
    assert ev(rule(), customer_id=None).valid


def test_usage_limit_checked_before_login_required() -> None:
    r = rule(max_uses_total=1, max_uses_per_customer=1)
    assert ev(r, customer_id=None, uses_total=1).reason == "promotions.coupon.usage_limit_reached"


def test_customer_limit_reached() -> None:
    r = rule(max_uses_per_customer=2)
    assert ev(r, uses_by_customer=2).reason == "promotions.coupon.customer_limit_reached"
    assert ev(r, uses_by_customer=1).valid


def test_allocate_remainder_goes_to_heaviest_then_lowest_id() -> None:
    items = [item("b", 100, 1), item("a", 100, 1), item("c", 100, 1)]
    out = allocate(100, items)
    assert out == {"a": 34, "b": 33, "c": 33}


def test_allocate_quantity_weight() -> None:
    out = allocate(10, [item("a", 100, 1), item("b", 100, 3)])
    assert out == {"a": 2, "b": 8}


def test_allocate_empty_or_zero() -> None:
    assert allocate(0, [item()]) == {"v1": 0}
    assert allocate(0, []) == {}


def _items_strategy(max_price: int, max_qty: int):
    return st.lists(
        st.builds(
            LineItem,
            variant_id=st.text(alphabet="abcdef", min_size=1, max_size=3),
            unit_price_cents=st.integers(min_value=1, max_value=max_price),
            quantity=st.integers(min_value=1, max_value=max_qty),
            category_slug=st.just("c"),
            collection_slugs=st.just(frozenset()),
        ),
        min_size=1,
        max_size=50,
        unique_by=lambda i: i.variant_id,
    )


def _check(items: list[LineItem], discount: int) -> None:
    out = allocate(discount, items)
    assert sum(out.values()) == discount
    assert out == allocate(discount, list(reversed(items)))
    for i in items:
        assert 0 <= out[i.variant_id] <= i.unit_price_cents * i.quantity


@st.composite
def _case(draw: st.DrawFn, max_price: int, max_qty: int) -> tuple[list[LineItem], int]:
    items = draw(_items_strategy(max_price, max_qty))
    total = sum(i.unit_price_cents * i.quantity for i in items)
    return items, draw(st.integers(min_value=0, max_value=total))


@given(case=_case(1_000_000, 20))
def test_allocate_property_large(case: tuple[list[LineItem], int]) -> None:
    _check(*case)


@example(case=([item("a", 1), item("b", 1), item("c", 1)], 2))
@example(case=([item("a", 1000), item("b", 1000), item("c", 1000)], 2999))
@given(case=_case(5, 3))
def test_allocate_property_small_ties(case: tuple[list[LineItem], int]) -> None:
    _check(*case)


def test_allocate_never_exceeds_item_weight_regressions() -> None:
    assert allocate(2, [item("a", 1), item("b", 1), item("c", 1)]) == {"a": 1, "b": 1, "c": 0}
    out = allocate(2999, [item("a", 1000), item("b", 1000), item("c", 1000)])
    assert out == {"a": 1000, "b": 1000, "c": 999}


def test_allocate_discount_above_total_raises() -> None:
    with pytest.raises(ValueError):
        allocate(5, [item("a", 1)])


def test_percent_over_100_clamped_to_subtotal() -> None:
    assert ev(rule(value=150), [item(price=1000)]).discount_cents == 1000


def test_naive_rule_dates_rejected() -> None:
    with pytest.raises(ValueError):
        ev(rule(starts_at=datetime(2026, 1, 1)))
    with pytest.raises(ValueError):
        ev(rule(ends_at=datetime(2027, 1, 1)))


def test_normalize_code_boundaries_and_non_ascii() -> None:
    assert normalize_code("abc") == "ABC"
    assert normalize_code("a" * 32) == "A" * 32
    with pytest.raises(ValueError):
        normalize_code("straße")
