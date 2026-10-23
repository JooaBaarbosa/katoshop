from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from ks_platform.health import health_router
from ks_platform.testing import run_migrations


async def test_postgres_url_accepts_connections(postgres_url):
    assert postgres_url.startswith("postgresql+asyncpg://")
    conn = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
    try:
        assert await conn.fetchval("SELECT 1") == 1
    finally:
        await conn.close()


async def test_asgi_client_factory_runs_lifespan(asgi_client_factory):
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        events.append("up")
        yield
        events.append("down")

    app = FastAPI(lifespan=lifespan)

    async def ok() -> bool:
        return True

    app.include_router(health_router(ok))
    async with asgi_client_factory(app) as client:
        assert events == ["up"]
        response = await client.get("/health/live")
    assert response.status_code == 200


_ENV = """
import asyncio
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

url = context.config.get_main_option("sqlalchemy.url")


def run(conn):
    context.configure(connection=conn, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


async def main():
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        await conn.run_sync(run)
    await engine.dispose()


asyncio.run(main())
"""

_REVISION = """
from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    op.execute("CREATE TABLE migrated (id int)")


def downgrade():
    op.execute("DROP TABLE migrated")
"""


async def test_run_migrations_works_inside_running_loop(postgres_url, tmp_path):
    (tmp_path / "versions").mkdir()
    (tmp_path / "env.py").write_text(_ENV)
    (tmp_path / "versions" / "0001_init.py").write_text(_REVISION)
    ini = tmp_path / "alembic.ini"
    ini.write_text(f"[alembic]\nscript_location = {tmp_path.as_posix()}\n")

    run_migrations(ini, postgres_url)

    conn = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
    try:
        assert await conn.fetchval("SELECT to_regclass('public.migrated')") == "migrated"
    finally:
        await conn.close()
