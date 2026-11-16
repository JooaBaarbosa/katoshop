"""Avaliação de cupom para o carrinho. Os usos vêm da contagem de resgates."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from promotions.application.ports import CouponRecord, UnitOfWorkFactory
from promotions.domain.coupons import (
    CouponRule,
    Evaluation,
    LineItem,
    evaluate,
    normalize_code,
)

NOT_FOUND_REASON = "promotions.coupon.not_found"


@dataclass(frozen=True)
class EvaluationResult:
    code: str
    evaluation: Evaluation
    items: list[LineItem]


def _rule(coupon: CouponRecord) -> CouponRule:
    return CouponRule(
        code=coupon.code,
        kind="percent" if coupon.kind == "percent" else "fixed",
        value=coupon.value,
        min_order_cents=coupon.min_order_cents,
        starts_at=coupon.starts_at,
        ends_at=coupon.ends_at,
        category_slugs=frozenset(coupon.category_slugs),
        collection_slugs=frozenset(coupon.collection_slugs),
        max_uses_total=coupon.max_uses_total,
        max_uses_per_customer=coupon.max_uses_per_customer,
        active=coupon.active,
    )


class EvaluateService:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    async def evaluate(
        self, raw_code: str, customer_id: uuid.UUID | None, items: list[LineItem]
    ) -> EvaluationResult:
        try:
            code = normalize_code(raw_code)
        except ValueError:
            return self._not_found(raw_code.strip().upper()[:32], items)
        async with self._uow() as uow:
            coupon = await uow.coupons.get_by_code(code)
            if coupon is None:
                return self._not_found(code, items)
            uses_total = await uow.coupons.count_uses(coupon.id)
            uses_by_customer = (
                await uow.coupons.count_uses(coupon.id, customer_id) if customer_id else 0
            )
        evaluation = evaluate(
            _rule(coupon),
            items,
            now=datetime.now(UTC),
            customer_id=str(customer_id) if customer_id else None,
            uses_total=uses_total,
            uses_by_customer=uses_by_customer,
        )
        return EvaluationResult(coupon.code, evaluation, items)

    @staticmethod
    def _not_found(code: str, items: list[LineItem]) -> EvaluationResult:
        return EvaluationResult(code, Evaluation(False, 0, {}, NOT_FOUND_REASON, None), items)
