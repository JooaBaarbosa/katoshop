import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Expressão da coluna gerada `products.search_vector`; a migração usa o mesmo texto.
SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('portuguese', immutable_unaccent(name)), 'A') || "
    "setweight(to_tsvector('portuguese', "
    "immutable_unaccent(coalesce(category_name_cache, ''))), 'B') || "
    "setweight(to_tsvector('portuguese', "
    "immutable_unaccent(coalesce(description, ''))), 'C')"
)


class Base(DeclarativeBase):
    pass


def _uuid7() -> uuid.UUID:
    return uuid.uuid7()


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=_uuid7)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = _pk()
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT")
    )
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Size(Base):
    __tablename__ = "sizes"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    label: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer)


class Color(Base):
    __tablename__ = "colors"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    hex: Mapped[str] = mapped_column(String(7))


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'active', 'archived')", name="ck_products_status"),
        CheckConstraint("base_price_cents >= 0", name="ck_products_base_price"),
        Index("ix_products_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_status_published_at", "status", "published_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT")
    )
    category_name_cache: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    base_price_cents: Mapped[int] = mapped_column(Integer)
    min_price_cents: Mapped[int | None] = mapped_column(Integer)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR, Computed(SEARCH_VECTOR_SQL, persisted=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Variant(Base):
    __tablename__ = "variants"
    __table_args__ = (
        UniqueConstraint("product_id", "color_code", "size_code", name="uq_variants_combo"),
        CheckConstraint(
            "stock_on_hand >= stock_reserved AND stock_reserved >= 0", name="ck_variants_stock"
        ),
        CheckConstraint("price_cents IS NULL OR price_cents >= 0", name="ck_variants_price"),
        Index("ix_variants_product_active", "product_id", "active"),
    )

    id: Mapped[uuid.UUID] = _pk()
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE")
    )
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    color_code: Mapped[str] = mapped_column(String(8), ForeignKey("colors.code"))
    size_code: Mapped[str] = mapped_column(String(8), ForeignKey("sizes.code"))
    price_cents: Mapped[int | None] = mapped_column(Integer)
    stock_on_hand: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    stock_reserved: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('initial', 'adjustment', 'damage', 'return', "
            "'reservation', 'release', 'sale')",
            name="ck_stock_movements_reason",
        ),
        Index("ix_stock_movements_variant_created", "variant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    variant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("variants.id", ondelete="RESTRICT")
    )
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created()


class ProductImage(Base):
    __tablename__ = "product_images"
    __table_args__ = (Index("ix_product_images_product_position", "product_id", "position"),)

    id: Mapped[uuid.UUID] = _pk()
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE")
    )
    color_code: Mapped[str | None] = mapped_column(String(8), ForeignKey("colors.code"))
    storage_key: Mapped[str] = mapped_column(Text)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    alt: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    credit_author: Mapped[str | None] = mapped_column(Text)
    credit_source_url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = _pk()
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class CollectionProduct(Base):
    __tablename__ = "collection_products"

    collection_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class StorefrontSettings(Base):
    __tablename__ = "storefront_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_storefront_settings_singleton"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = _updated()
