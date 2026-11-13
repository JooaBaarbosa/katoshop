"""Plugin pytest compartilhado. Requer o extra `katoshop-platform[testing]`."""

import warnings
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, contextmanager
from pathlib import Path
from threading import Thread

import httpx
import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer

RABBITMQ_IMAGE = "rabbitmq:4.4.0-management-alpine"
REDIS_IMAGE = "redis:8.10.3-alpine"


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


@contextmanager
def _legacy_wait_allowed() -> Iterator[None]:
    """Os containers de RabbitMQ e Redis do testcontainers 4.15 ainda usam o decorator
    `@wait_container_is_ready`, que emite DeprecationWarning na importação e na espera."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="The @wait_container_is_ready decorator is deprecated",
            category=DeprecationWarning,
        )
        yield


@pytest.fixture(scope="session")
def rabbitmq_container() -> Iterator[DockerContainer]:
    """Container do broker; use `.exec(["rabbitmqctl", ...])` para simular quedas."""
    with _legacy_wait_allowed():
        from testcontainers.community.rabbitmq import RabbitMqContainer

        rabbit = RabbitMqContainer(RABBITMQ_IMAGE).start()
    try:
        yield rabbit
    finally:
        rabbit.stop()


@pytest.fixture(scope="session")
def rabbitmq_url(rabbitmq_container: DockerContainer) -> str:
    host = rabbitmq_container.get_container_host_ip()
    port = rabbitmq_container.get_exposed_port(5672)
    return f"amqp://guest:guest@{host}:{port}/"


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with _legacy_wait_allowed():
        from testcontainers.community.redis import RedisContainer

        redis = RedisContainer(REDIS_IMAGE).start()
    try:
        host = redis.get_container_host_ip()
        port = redis.get_exposed_port(redis.port)
        yield f"redis://{host}:{port}/0"
    finally:
        redis.stop()


@pytest.fixture
def asgi_client_factory() -> Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]]:
    @asynccontextmanager
    async def make_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
        async with LifespanManager(app):
            transport = httpx.ASGITransport(app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                yield client

    return make_client
