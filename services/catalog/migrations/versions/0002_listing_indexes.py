"""índices da listagem pública: ordenação por preço e coleção por produto

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Ordenação price_asc/price_desc da vitrine (sempre com status = 'active').
    op.create_index("ix_products_status_min_price", "products", ["status", "min_price_cents", "id"])
    # A PK (collection_id, product_id) não atende buscas e cascatas a partir do produto.
    op.create_index("ix_collection_products_product_id", "collection_products", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_collection_products_product_id", table_name="collection_products")
    op.drop_index("ix_products_status_min_price", table_name="products")
