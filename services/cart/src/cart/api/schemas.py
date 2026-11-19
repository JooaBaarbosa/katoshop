import uuid
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from cart.application.cart_service import CartView
from cart.domain.cart import CartItem, MergeResult


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AddItemIn(_In):
    variant_id: uuid.UUID
    # O teto real (max_qty e estoque) é regra do domínio, com o máximo na resposta 422.
    quantity: int = Field(ge=1, le=1000)


class QuantityIn(_In):
    quantity: int = Field(ge=0, le=1000)


class CouponIn(_In):
    code: str = Field(max_length=64)


class MergeIn(_In):
    guest_cart_id: str = Field(max_length=64)


class NoticeOut(BaseModel):
    code: Literal["price_changed", "quantity_reduced", "unavailable"]
    old_price_cents: int | None
    new_price_cents: int | None
    quantity: int | None


class ItemOut(BaseModel):
    variant_id: str
    product_id: str
    product_slug: str
    name: str
    color_code: str
    color_name: str
    size_code: str
    image_url: str | None
    unit_price_cents: int
    quantity: int
    available: int
    unavailable: bool
    line_discount_cents: int
    notice: NoticeOut | None

    @classmethod
    def from_item(cls, item: CartItem, line_discount_cents: int) -> Self:
        notice = item.notice
        return cls(
            variant_id=item.variant_id,
            product_id=item.product_id,
            product_slug=item.product_slug,
            name=item.name,
            color_code=item.color_code,
            color_name=item.color_name,
            size_code=item.size_code,
            image_url=item.image_url,
            unit_price_cents=item.unit_price_cents,
            quantity=item.quantity,
            available=item.available,
            unavailable=item.unavailable,
            line_discount_cents=line_discount_cents,
            notice=None
            if notice is None
            else NoticeOut(
                code=notice.code,
                old_price_cents=notice.old_price_cents,
                new_price_cents=notice.new_price_cents,
                quantity=notice.quantity,
            ),
        )


class CouponOut(BaseModel):
    code: str
    valid: bool
    reason: str | None
    min_order_cents: int | None


class CartOut(BaseModel):
    cart_id: str | None
    items: list[ItemOut]
    subtotal_cents: int
    discount_cents: int
    total_cents: int
    coupon: CouponOut | None
    checkout_blocked: bool

    @classmethod
    def from_view(cls, view: CartView) -> Self:
        cart = view.cart
        # Hash do Redis não guarda ordem: variant_id (UUIDv7) dá uma ordem estável.
        items = sorted(cart.items.values(), key=lambda i: i.variant_id) if cart else []
        coupon = view.coupon
        return cls(
            cart_id=cart.cart_id if cart else None,
            items=[ItemOut.from_item(i, view.line_discounts.get(i.variant_id, 0)) for i in items],
            subtotal_cents=view.subtotal_cents,
            discount_cents=view.discount_cents,
            total_cents=view.total_cents,
            coupon=None
            if coupon is None
            else CouponOut(
                code=coupon.code,
                valid=coupon.valid,
                reason=coupon.reason,
                min_order_cents=coupon.min_order_cents,
            ),
            checkout_blocked=view.checkout_blocked,
        )


class MergeReportOut(BaseModel):
    reduced: list[str]
    dropped: list[str]


class MergeOut(CartOut):
    merge_report: MergeReportOut

    @classmethod
    def from_merge(cls, view: CartView, report: MergeResult) -> Self:
        base = CartOut.from_view(view)
        return cls(
            **base.model_dump(),
            merge_report=MergeReportOut(reduced=report.reduced, dropped=report.dropped),
        )
