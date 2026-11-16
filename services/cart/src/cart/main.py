from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from cart.settings import CartSettings
from ks_platform.errors import install_problem_handlers
from ks_platform.health import health_router
from ks_platform.observability import configure_logging, configure_observability


def create_app(settings: CartSettings | None = None, redis_client: Redis | None = None) -> FastAPI:
    settings = settings or CartSettings()  # pyright: ignore[reportCallIssue]
    configure_logging(settings.service_name, settings.log_level)
    owns_redis = redis_client is None
    redis = redis_client or Redis.from_url(
        settings.redis_url, socket_connect_timeout=2, socket_timeout=2
    )

    async def ready_check() -> bool:
        return bool(await redis.ping())

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if owns_redis:
                await redis.aclose()

    app = FastAPI(title="KatoShop cart", lifespan=lifespan)
    app.state.settings = settings
    app.state.redis = redis
    install_problem_handlers(app)
    configure_observability(app, settings)
    app.include_router(health_router(ready_check))
    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn cart.main:app` carrega as settings do ambiente sob demanda.
    if name == "app":
        return create_app()
    raise AttributeError(name)
