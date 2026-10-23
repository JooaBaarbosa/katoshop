from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from identity.main import create_app
from identity.settings import IdentitySettings

pytest_plugins = ["ks_platform.testing"]

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> str:
    from ks_platform.testing import run_migrations  # noqa: PLC0415

    run_migrations(ALEMBIC_INI, postgres_url)
    return postgres_url


@pytest.fixture
def settings(migrated_url: str, tmp_path: Path) -> IdentitySettings:
    return IdentitySettings(
        database_url=migrated_url,
        signing_key_path=tmp_path / "signing-key.pem",
    )


@pytest.fixture
def app(settings: IdentitySettings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(
    app: FastAPI,
    asgi_client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> AsyncIterator[httpx.AsyncClient]:
    async with asgi_client_factory(app) as http_client:
        yield http_client
