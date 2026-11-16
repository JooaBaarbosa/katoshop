"""Domínio puro de cupons: normalização, avaliação de regras e rateio."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

_CODE_RE = re.compile(r"^[A-Z0-9-]{3,32}$")
_PREFIX = "promotions.coupon."


def normalize_code(raw: str) -> str:
    code = raw.strip().upper()
    if not _CODE_RE.fullmatch(code):
        raise ValueError("invalid coupon code")
    return code


@dataclass(frozen=True)
class CouponRule:
    code: str
    kind: Literal["percent", "fixed"]
    value: int
    min_order_cents: int | None
    starts_at: datetime | None
    ends_at: datetime | None
    category_slugs: frozenset[str]
    collection_slugs: frozenset[str]
    max_uses_total: int | None
    max_uses_per_customer: int | None
    active: bool


@dataclass(frozen=True)
class LineItem:
    variant_id: str
    unit_price_cents: int
    quantity: int
    category_slug: str
    collection_slugs: frozenset[str]

    @property
    def weight(self) -> int:
        return self.unit_price_cents * self.quantity


@dataclass(frozen=True)
class Evaluation:
    valid: bool
    discount_cents: int
    per_item: dict[str, int]
    reason: str | None
    min_order_cents: int | None


def _invalid(reason: str, min_order_cents: int | None = None) -> Evaluation:
    return Evaluation(False, 0, {}, _PREFIX + reason, min_order_cents)


def _is_eligible(rule: CouponRule, item: LineItem) -> bool:
    if not rule.category_slugs and not rule.collection_slugs:
        return True
    return item.category_slug in rule.category_slugs or bool(
        item.collection_slugs & rule.collection_slugs
    )


def allocate(discount_cents: int, eligible: list[LineItem]) -> dict[str, int]:
    total = sum(i.weight for i in eligible)
    if not eligible or total == 0:
        return {i.variant_id: 0 for i in eligible}
    parts = {i.variant_id: discount_cents * i.weight // total for i in eligible}
    remainder = discount_cents - sum(parts.values())
    if remainder:
        top = min(eligible, key=lambda i: (-i.weight, i.variant_id))
        parts[top.variant_id] += remainder
    return parts


def evaluate(
    rule: CouponRule,
    items: list[LineItem],
    *,
    now: datetime,
    customer_id: str | None,
    uses_total: int,
    uses_by_customer: int,
) -> Evaluation:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if not items:
        raise ValueError("items must not be empty")
    if not rule.active:
        return _invalid("inactive")
    if rule.starts_at is not None and now < rule.starts_at:
        return _invalid("not_started")
    if rule.ends_at is not None and now >= rule.ends_at:
        return _invalid("expired")
    eligible = [i for i in items if _is_eligible(rule, i)]
    if not eligible:
        return _invalid("no_eligible_items")
    subtotal = sum(i.weight for i in eligible)
    if rule.min_order_cents is not None and subtotal < rule.min_order_cents:
        return _invalid("min_order_not_met", rule.min_order_cents)
    if rule.max_uses_total is not None and uses_total >= rule.max_uses_total:
        return _invalid("usage_limit_reached")
    if rule.max_uses_per_customer is not None:
        if customer_id is None:
            return _invalid("login_required")
        if uses_by_customer >= rule.max_uses_per_customer:
            return _invalid("customer_limit_reached")
    discount = subtotal * rule.value // 100 if rule.kind == "percent" else min(rule.value, subtotal)
    return Evaluation(True, discount, allocate(discount, eligible), None, None)
