from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from identity.adapters.models import SigningKey as SigningKeyRow
from identity.adapters.repositories import (
    SessionScope,
    SqlRefreshTokenRepository,
    SqlUserRepository,
)
from identity.adapters.signing import load_signing_key
from identity.api.routes_auth import router as auth_router
from identity.api.routes_jwks import router as jwks_router
from identity.api.routes_me import router as me_router
from identity.application.auth_service import AuthService
from identity.domain.passwords import validate_password
from identity.settings import IdentitySettings
from ks_platform.auth import JwksKeyProvider, TokenVerifier
from ks_platform.db import make_engine, make_session_factory
from ks_platform.errors import install_db_error_handler, install_problem_handlers
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

    scope = SessionScope(session_factory)
    auth = AuthService(
        SqlUserRepository(scope),
        SqlRefreshTokenRepository(scope),
        signing_key,
        lambda: datetime.now(UTC),
    )

    async def local_jwks(_url: str) -> dict[str, Any]:
        # o identity verifica os próprios tokens em processo, sem HTTP para si mesmo
        return {"keys": [signing_key.public_jwk()]}

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
            if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
                violations = validate_password(
                    settings.bootstrap_admin_password, settings.bootstrap_admin_email.strip()
                )
                if violations:
                    raise RuntimeError(
                        "IDENTITY_BOOTSTRAP_ADMIN_PASSWORD viola a política de senha: "
                        + ", ".join(violations)
                    )
                await auth.ensure_bootstrap_admin(
                    settings.bootstrap_admin_email, settings.bootstrap_admin_password
                )
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="KatoShop identity", lifespan=lifespan)
    app.state.signing_key = signing_key
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.auth_service = auth
    app.state.token_verifier = TokenVerifier(JwksKeyProvider(settings.jwks_url, fetch=local_jwks))
    install_problem_handlers(app)
    install_db_error_handler(app)
    configure_observability(app, settings, engine)
    app.include_router(health_router(ready_check))
    app.include_router(jwks_router)
    app.include_router(auth_router)
    app.include_router(me_router)
    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn identity.main:app` carrega as settings do ambiente sob demanda.
    if name == "app":
        return create_app()
    raise AttributeError(name)
