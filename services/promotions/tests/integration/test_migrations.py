import httpx
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from promotions.adapters.models import Base

INSERT = (
    "INSERT INTO coupons (id, code, kind, value{extra_cols}) "
    "VALUES (gen_random_uuid(), :code, :kind, :value{extra_vals})"
)


async def test_upgrade_creates_tables(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
            rules = (
                await conn.execute(
                    text(
                        "SELECT conrelid::regclass::text, confrelid::regclass::text, "
                        "confdeltype::text FROM pg_constraint WHERE contype = 'f'"
                    )
                )
            ).all()
    finally:
        await engine.dispose()
    assert {"coupons", "coupon_redemptions"} <= tables
    assert {(r[0], r[1]): r[2] for r in rules}[("coupon_redemptions", "coupons")] == "r"


@pytest.mark.parametrize(
    ("code", "kind", "value", "extra"),
    [
        ("PCT91", "percent", 91, ""),
        ("ZERO", "fixed", 0, ""),
        ("zero-lower", "fixed", 100, ""),
        ("AB", "fixed", 100, ""),
        ("BAD_CHAR", "fixed", 100, ""),
        ("KIND", "bogus", 10, ""),
        ("ENDS", "fixed", 100, ", starts_at, ends_at"),
        ("MINZ", "fixed", 100, ", min_order_cents"),
        ("USEZ", "fixed", 100, ", max_uses_total"),
        ("CUSTZ", "fixed", 100, ", max_uses_per_customer"),
    ],
)
async def test_checks_reject_invalid_rows(
    migrated_url: str, code: str, kind: str, value: int, extra: str
) -> None:
    params: dict[str, object] = {"code": code, "kind": kind, "value": value}
    if "starts_at" in extra:
        extra_vals = ", '2026-12-02T00:00:00Z', '2026-12-01T00:00:00Z'"
    elif extra:
        extra_vals = ", 0"
    else:
        extra_vals = ""
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn:
            with pytest.raises(IntegrityError):
                await conn.execute(
                    text(INSERT.format(extra_cols=extra, extra_vals=extra_vals)), params
                )
            await conn.rollback()
    finally:
        await engine.dispose()


async def test_valid_coupon_and_unique_code(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn:
            sql = text(INSERT.format(extra_cols="", extra_vals=""))
            await conn.execute(sql, {"code": "BEMVINDO10", "kind": "percent", "value": 90})
            row = (
                await conn.execute(
                    text("SELECT category_slugs, collection_slugs, active, version FROM coupons")
                )
            ).one()
            with pytest.raises(IntegrityError):
                await conn.execute(sql, {"code": "BEMVINDO10", "kind": "fixed", "value": 5})
            await conn.rollback()
    finally:
        await engine.dispose()
    assert tuple(row) == ([], [], True, 1)


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
