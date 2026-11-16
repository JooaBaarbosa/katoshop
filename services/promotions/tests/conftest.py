from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from promotions.main import create_app
from promotions.settings import PromotionsSettings

pytest_plugins = ["ks_platform.testing"]

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> str:
    from ks_platform.testing import run_migrations  # noqa: PLC0415

    run_migrations(ALEMBIC_INI, postgres_url)
    return postgres_url


@pytest.fixture
def settings(migrated_url: str) -> PromotionsSettings:
    return PromotionsSettings(database_url=migrated_url)


@pytest.fixture
def app(settings: PromotionsSettings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(
    app: FastAPI,
    asgi_client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> AsyncIterator[httpx.AsyncClient]:
    async with asgi_client_factory(app) as http_client:
        yield http_client
