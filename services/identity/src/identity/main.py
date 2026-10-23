from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from identity.adapters.models import SigningKey as SigningKeyRow
from identity.adapters.signing import load_signing_key
from identity.api.routes_jwks import router as jwks_router
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

    signing_key = load_signing_key(settings.signing_key_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            public_jwk = signing_key.public_jwk()
            async with session_factory() as session, session.begin():
                await session.execute(
                    insert(SigningKeyRow)
                    .values(
                        kid=signing_key.kid,
                        public_jwk=public_jwk,
                        private_key_ref=str(settings.signing_key_path),
                        active=True,
                    )
                    .on_conflict_do_update(
                        index_elements=[SigningKeyRow.kid],
                        set_={
                            "public_jwk": public_jwk,
                            "private_key_ref": str(settings.signing_key_path),
                            "active": True,
                        },
                    )
                )
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="KatoShop identity", lifespan=lifespan)
    app.state.signing_key = signing_key
    app.state.settings = settings
    app.state.session_factory = session_factory
    install_problem_handlers(app)
    configure_observability(app, settings, engine)
    app.include_router(health_router(ready_check))
    app.include_router(jwks_router)
    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn identity.main:app` carrega as settings do ambiente sob demanda.
    if name == "app":
        return create_app()
    raise AttributeError(name)
