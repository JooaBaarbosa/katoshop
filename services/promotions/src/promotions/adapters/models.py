import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid7() -> uuid.UUID:
    return uuid.uuid7()


class Coupon(Base):
    __tablename__ = "coupons"
    __table_args__ = (
        CheckConstraint("kind IN ('percent', 'fixed')", name="ck_coupons_kind"),
        CheckConstraint("value > 0", name="ck_coupons_value_positive"),
        CheckConstraint("kind <> 'percent' OR value <= 90", name="ck_coupons_percent_max"),
        CheckConstraint("code ~ '^[A-Z0-9-]{3,32}$'", name="ck_coupons_code_format"),
        CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at",
            name="ck_coupons_period",
        ),
        CheckConstraint(
            "min_order_cents IS NULL OR min_order_cents > 0", name="ck_coupons_min_order"
        ),
        CheckConstraint(
            "max_uses_total IS NULL OR max_uses_total > 0", name="ck_coupons_max_uses_total"
        ),
        CheckConstraint(
            "max_uses_per_customer IS NULL OR max_uses_per_customer > 0",
            name="ck_coupons_max_uses_per_customer",
        ),
        Index("ix_coupons_code", "code", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=_uuid7)
    code: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    kind: Mapped[str] = mapped_column(String(16))
    value: Mapped[int] = mapped_column(Integer)
    min_order_cents: Mapped[int | None] = mapped_column(Integer)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    category_slugs: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'")
    )
    collection_slugs: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'")
    )
    max_uses_total: Mapped[int | None] = mapped_column(Integer)
    max_uses_per_customer: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CouponRedemption(Base):
    __tablename__ = "coupon_redemptions"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_coupon_redemptions_order_id"),
        Index("ix_coupon_redemptions_coupon_customer", "coupon_id", "customer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=_uuid7)
    coupon_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("coupons.id", ondelete="RESTRICT")
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True))
    order_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
