import httpx
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from catalog.adapters.models import Base

EXPECTED_TABLES = {
    "categories",
    "sizes",
    "colors",
    "products",
    "variants",
    "stock_movements",
    "product_images",
    "collections",
    "collection_products",
    "storefront_settings",
}

# Nada é excluído da comparação. O alembic não compara colunas geradas (Computed), CHECKs nem
# funções SQL: `products.search_vector` e `immutable_unaccent` são cobertos pelos testes de
# comportamento de busca; o índice GIN, FKs, índices e tipos são comparados normalmente.


async def test_upgrade_creates_tables_and_reference_data(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
            sizes = (await conn.execute(text("SELECT code FROM sizes ORDER BY position"))).scalars()
            sizes = list(sizes)
            colors = (
                await conn.execute(text("SELECT code, name, hex FROM colors ORDER BY code"))
            ).all()
    finally:
        await engine.dispose()
    assert EXPECTED_TABLES <= tables
    assert sizes == ["PP", "P", "M", "G", "GG", "XG", "XGG"]
    assert len(colors) == 7
    assert ("PRT", "Preto", "#111111") in [tuple(c) for c in colors]
    assert ("CNZ", "Cinza mescla", "#8C8C88") in [tuple(c) for c in colors]


async def _insert_product_with_variant(conn, name: str, slug: str) -> None:
    await conn.execute(
        text(
            "INSERT INTO categories (id, slug, name, position) "
            "VALUES (gen_random_uuid(), :cs, 'Moletons', 0) ON CONFLICT DO NOTHING"
        ),
        {"cs": f"cat-{slug}"},
    )
    await conn.execute(
        text(
            "INSERT INTO products (id, slug, name, description, category_id, status, "
            "base_price_cents, category_name_cache) "
            "SELECT gen_random_uuid(), :slug, :name, 'Algodão pesado', id, 'draft', 19900, "
            "'Moletons' "
            "FROM categories WHERE slug = :cs"
        ),
        {"slug": slug, "name": name, "cs": f"cat-{slug}"},
    )


async def test_search_vector_ignores_accents(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn:
            await _insert_product_with_variant(conn, "Moletom Básico", "moletom-basico")
            found = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM products WHERE search_vector @@ "
                        "websearch_to_tsquery('portuguese', immutable_unaccent(:q)) "
                        "AND slug = 'moletom-basico'"
                    ),
                    {"q": "basico"},
                )
            ).scalar_one()
            await conn.rollback()
    finally:
        await engine.dispose()
    assert found == 1


async def test_stock_check_constraint(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn:
            await _insert_product_with_variant(conn, "Camiseta Teste", "camiseta-teste-stock")
            await conn.execute(
                text(
                    "INSERT INTO variants (id, product_id, sku, color_code, size_code) "
                    "SELECT gen_random_uuid(), id, 'SKU-STOCK-1', 'PRT', 'M' "
                    "FROM products WHERE slug = 'camiseta-teste-stock'"
                )
            )
            try:
                await conn.execute(
                    text("UPDATE variants SET stock_on_hand = -1 WHERE sku = 'SKU-STOCK-1'")
                )
            except IntegrityError:
                raised = True
            else:
                raised = False
            await conn.rollback()
    finally:
        await engine.dispose()
    assert raised


async def test_foreign_key_delete_rules(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT conrelid::regclass::text, confrelid::regclass::text, "
                        "confdeltype::text "
                        "FROM pg_constraint WHERE contype = 'f'"
                    )
                )
            ).all()
    finally:
        await engine.dispose()
    rules = {(r[0], r[1]): r[2] for r in rows}
    assert rules[("variants", "products")] == "c"
    assert rules[("product_images", "products")] == "c"
    assert rules[("collection_products", "products")] == "c"
    assert rules[("collection_products", "collections")] == "c"
    assert rules[("products", "categories")] == "r"
    assert rules[("stock_movements", "variants")] == "r"


async def test_ready_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200


async def test_models_match_migrations(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn:
            diff = await conn.run_sync(
                lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata)
            )
    finally:
        await engine.dispose()
    assert diff == []
