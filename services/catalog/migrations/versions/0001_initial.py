"""tabelas iniciais do catalog, busca em portuguÃªs e dados de referÃªncia

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

# Cópia congelada: a migração não importa o código da aplicação.
SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('portuguese', immutable_unaccent(name)), 'A') || "
    "setweight(to_tsvector('portuguese', "
    "immutable_unaccent(coalesce(category_name_cache, ''))), 'B') || "
    "setweight(to_tsvector('portuguese', "
    "immutable_unaccent(coalesce(description, ''))), 'C')"
)

SIZES = ["PP", "P", "M", "G", "GG", "XG", "XGG"]
COLORS = [
    ("PRT", "Preto", "#111111"),
    ("BRC", "Branco", "#F4F4F0"),
    ("CNZ", "Cinza mescla", "#8C8C88"),
    ("OFW", "Off-white", "#E8E3D6"),
    ("VRD", "Verde musgo", "#4A5236"),
    ("AZM", "Azul marinho", "#1E2A44"),
    ("MRR", "Marrom", "#5A4030"),
]


def _uuid_pk() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)


def upgrade() -> None:
    now = sa.text("now()")
    # Idempotente: o init do Postgres no compose tambÃ©m cria a extensÃ£o.
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    # unaccent() Ã© STABLE; o wrapper IMMUTABLE Ã© necessÃ¡rio para coluna gerada e Ã­ndice.
    op.execute(
        "CREATE OR REPLACE FUNCTION public.immutable_unaccent(text) RETURNS text "
        "LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT "
        "AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$"
    )

    op.create_table(
        "categories",
        _uuid_pk(),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
        ),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
    )
    sizes = op.create_table(
        "sizes",
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("label", sa.String(32), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
    )
    colors = op.create_table(
        "colors",
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("hex", sa.String(7), nullable=False),
    )
    op.bulk_insert(
        sizes,
        [{"code": c, "label": c, "position": i} for i, c in enumerate(SIZES, start=1)],
    )
    op.bulk_insert(colors, [{"code": c, "name": n, "hex": h} for c, n, h in COLORS])

    op.create_table(
        "products",
        _uuid_pk(),
        sa.Column("slug", sa.String(160), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("category_name_cache", sa.Text),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("base_price_cents", sa.Integer, nullable=False),
        sa.Column("min_price_cents", sa.Integer),
        sa.Column("attributes", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR,
            sa.Computed(SEARCH_VECTOR_SQL, persisted=True),
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.CheckConstraint("status IN ('draft', 'active', 'archived')", name="ck_products_status"),
        sa.CheckConstraint("base_price_cents >= 0", name="ck_products_base_price"),
    )
    op.create_index(
        "ix_products_search_vector", "products", ["search_vector"], postgresql_using="gin"
    )
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index("ix_products_status_published_at", "products", ["status", "published_at"])

    op.create_table(
        "variants",
        _uuid_pk(),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sku", sa.String(64), nullable=False, unique=True),
        sa.Column("color_code", sa.String(8), sa.ForeignKey("colors.code"), nullable=False),
        sa.Column("size_code", sa.String(8), sa.ForeignKey("sizes.code"), nullable=False),
        sa.Column("price_cents", sa.Integer),
        sa.Column("stock_on_hand", sa.Integer, nullable=False, server_default="0"),
        sa.Column("stock_reserved", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.UniqueConstraint("product_id", "color_code", "size_code", name="uq_variants_combo"),
        sa.CheckConstraint(
            "stock_on_hand >= stock_reserved AND stock_reserved >= 0", name="ck_variants_stock"
        ),
        sa.CheckConstraint("price_cents IS NULL OR price_cents >= 0", name="ck_variants_price"),
    )
    op.create_index("ix_variants_product_active", "variants", ["product_id", "active"])

    op.create_table(
        "stock_movements",
        _uuid_pk(),
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("variants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("delta", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(16), nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.CheckConstraint(
            "reason IN ('initial', 'adjustment', 'damage', 'return', "
            "'reservation', 'release', 'sale')",
            name="ck_stock_movements_reason",
        ),
    )
    op.create_index(
        "ix_stock_movements_variant_created", "stock_movements", ["variant_id", "created_at"]
    )

    op.create_table(
        "product_images",
        _uuid_pk(),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("color_code", sa.String(8), sa.ForeignKey("colors.code")),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("alt", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("credit_author", sa.Text),
        sa.Column("credit_source_url", sa.Text),
        sa.Column("license", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
    )
    op.create_index(
        "ix_product_images_product_position", "product_images", ["product_id", "position"]
    )

    op.create_table(
        "collections",
        _uuid_pk(),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("featured", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_table(
        "collection_products",
        sa.Column(
            "collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_table(
        "storefront_settings",
        sa.Column("id", sa.SmallInteger, primary_key=True),
        sa.Column("data", postgresql.JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.CheckConstraint("id = 1", name="ck_storefront_settings_singleton"),
    )


def downgrade() -> None:
    for table in (
        "storefront_settings",
        "collection_products",
        "collections",
        "product_images",
        "stock_movements",
        "variants",
        "products",
        "colors",
        "sizes",
        "categories",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS public.immutable_unaccent(text)")
