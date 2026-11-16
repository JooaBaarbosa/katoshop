from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from ks_platform.auth import JwksKeyProvider, TokenVerifier
from ks_platform.db import make_engine, make_session_factory
from ks_platform.errors import install_db_error_handler, install_problem_handlers
from ks_platform.health import health_router
from ks_platform.observability import configure_logging, configure_observability
from promotions.adapters.repositories import sql_unit_of_work
from promotions.api.routes_admin import router as admin_router
from promotions.api.routes_evaluate import router as evaluate_router
from promotions.application.admin_service import AdminCouponService
from promotions.application.evaluate_service import EvaluateService
from promotions.settings import PromotionsSettings


def create_app(settings: PromotionsSettings | None = None) -> FastAPI:
    settings = settings or PromotionsSettings()  # pyright: ignore[reportCallIssue]
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

    app = FastAPI(title="KatoShop promotions", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    uow = sql_unit_of_work(session_factory)
    app.state.admin_service = AdminCouponService(uow)
    app.state.evaluate_service = EvaluateService(uow)
    app.state.token_verifier = TokenVerifier(JwksKeyProvider(settings.jwks_url))
    install_problem_handlers(app)
    install_db_error_handler(app)
    configure_observability(app, settings, engine)
    app.include_router(health_router(ready_check))
    app.include_router(admin_router)
    app.include_router(evaluate_router)
    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn promotions.main:app` carrega as settings do ambiente sob demanda.
    if name == "app":
        return create_app()
    raise AttributeError(name)
