"""cupons e resgates

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coupons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("value", sa.Integer, nullable=False),
        sa.Column("min_order_cents", sa.Integer),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("category_slugs", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column(
            "collection_slugs", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"
        ),
        sa.Column("max_uses_total", sa.Integer),
        sa.Column("max_uses_per_customer", sa.Integer),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("kind IN ('percent', 'fixed')", name="ck_coupons_kind"),
        sa.CheckConstraint("value > 0", name="ck_coupons_value_positive"),
        sa.CheckConstraint("kind <> 'percent' OR value <= 90", name="ck_coupons_percent_max"),
        sa.CheckConstraint("code ~ '^[A-Z0-9-]{3,32}$'", name="ck_coupons_code_format"),
        sa.CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at",
            name="ck_coupons_period",
        ),
        sa.CheckConstraint(
            "min_order_cents IS NULL OR min_order_cents > 0", name="ck_coupons_min_order"
        ),
        sa.CheckConstraint(
            "max_uses_total IS NULL OR max_uses_total > 0", name="ck_coupons_max_uses_total"
        ),
        sa.CheckConstraint(
            "max_uses_per_customer IS NULL OR max_uses_per_customer > 0",
            name="ck_coupons_max_uses_per_customer",
        ),
    )
    op.create_index("ix_coupons_code", "coupons", ["code"], unique=True)

    op.create_table(
        "coupon_redemptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "coupon_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("coupons.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("order_id", name="uq_coupon_redemptions_order_id"),
    )
    op.create_index(
        "ix_coupon_redemptions_coupon_customer", "coupon_redemptions", ["coupon_id", "customer_id"]
    )


def downgrade() -> None:
    op.drop_table("coupon_redemptions")
    op.drop_table("coupons")
