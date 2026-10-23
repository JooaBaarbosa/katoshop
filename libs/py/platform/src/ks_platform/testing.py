"""Plugin pytest compartilhado. Requer o extra `katoshop-platform[testing]`."""

from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from threading import Thread

import httpx
import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from testcontainers.community.postgres import PostgresContainer


def run_migrations(alembic_ini: Path, url: str) -> None:
    """Aplica `upgrade head`. Roda em thread própria: o env.py async cria seu próprio loop."""
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", url)
    errors: list[BaseException] = []

    def work() -> None:
        try:
            command.upgrade(cfg, "head")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = Thread(target=work)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:18.6-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture
def asgi_client_factory() -> Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]]:
    @asynccontextmanager
    async def make_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
        async with LifespanManager(app):
            transport = httpx.ASGITransport(app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                yield client

    return make_client
