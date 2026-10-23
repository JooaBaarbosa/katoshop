import httpx
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

EXPECTED_TABLES = {"users", "roles", "user_roles", "refresh_tokens", "signing_keys"}


async def test_upgrade_creates_tables(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
            roles = (await conn.execute(text("SELECT key FROM roles"))).scalars().all()
    finally:
        await engine.dispose()
    assert EXPECTED_TABLES <= tables
    assert list(roles) == ["admin"]


async def test_schema_constraints(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn:
            indexes = await conn.run_sync(
                lambda sync: {
                    table: inspect(sync).get_indexes(table) for table in ("users", "refresh_tokens")
                }
            )
            columns = await conn.run_sync(
                lambda sync: {c["name"] for c in inspect(sync).get_columns("refresh_tokens")}
            )
            defs = (
                (
                    await conn.execute(
                        text("SELECT indexdef FROM pg_indexes WHERE tablename = 'users'")
                    )
                )
                .scalars()
                .all()
            )
    finally:
        await engine.dispose()
    assert any("lower((email)::text)" in d and "UNIQUE" in d for d in defs)
    assert any(i["column_names"] == ["family_id"] for i in indexes["refresh_tokens"])
    assert "first_used_at" in columns


async def test_ready_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
