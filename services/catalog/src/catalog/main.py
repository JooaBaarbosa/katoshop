from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from catalog.settings import CatalogSettings
from ks_platform.auth import JwksKeyProvider, TokenVerifier
from ks_platform.db import make_engine, make_session_factory
from ks_platform.errors import install_problem_handlers
from ks_platform.health import health_router
from ks_platform.observability import configure_logging, configure_observability


def create_app(settings: CatalogSettings | None = None) -> FastAPI:
    settings = settings or CatalogSettings()  # pyright: ignore[reportCallIssue]
    configure_logging(settings.service_name, settings.log_level)
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    async def ready_check() -> bool:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="KatoShop catalog", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.token_verifier = TokenVerifier(JwksKeyProvider(settings.jwks_url))
    install_problem_handlers(app)
    configure_observability(app, settings, engine)
    app.include_router(health_router(ready_check))
    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn catalog.main:app` carrega as settings do ambiente sob demanda.
    if name == "app":
        return create_app()
    raise AttributeError(name)
