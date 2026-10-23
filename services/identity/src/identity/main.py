from fastapi import FastAPI
from sqlalchemy import text

from identity.settings import IdentitySettings
from ks_platform.db import make_engine, make_session_factory
from ks_platform.errors import install_problem_handlers
from ks_platform.health import health_router
from ks_platform.observability import configure_logging, configure_observability


def create_app(settings: IdentitySettings | None = None) -> FastAPI:
    settings = settings or IdentitySettings()  # pyright: ignore[reportCallIssue]
    configure_logging(settings.service_name, settings.log_level)
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    async def ready_check() -> bool:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True

    app = FastAPI(title="KatoShop identity")
    app.state.settings = settings
    app.state.session_factory = session_factory
    install_problem_handlers(app)
    configure_observability(app, settings, engine)
    app.include_router(health_router(ready_check))
    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn identity.main:app` carrega as settings do ambiente sob demanda.
    if name == "app":
        return create_app()
    raise AttributeError(name)
