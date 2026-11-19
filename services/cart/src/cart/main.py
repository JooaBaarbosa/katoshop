from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from cart.adapters.catalog_client import CatalogClient
from cart.adapters.promotions_client import PromotionsClient
from cart.adapters.redis_repo import RedisCartRepository
from cart.api.errors import install_cart_error_handler
from cart.api.routes import router as cart_router
from cart.application.ports import CatalogPort, PromotionsPort
from cart.settings import CartSettings
from ks_platform.auth import JwksKeyProvider, TokenVerifier
from ks_platform.errors import install_problem_handlers
from ks_platform.health import health_router
from ks_platform.http import make_http_client
from ks_platform.observability import configure_logging, configure_observability
from ks_platform.service_tokens import ServiceTokenProvider

UPSTREAM_TIMEOUT_S = 2.0


def create_app(
    settings: CartSettings | None = None,
    redis_client: Redis | None = None,
    *,
    catalog: CatalogPort | None = None,
    promotions: PromotionsPort | None = None,
) -> FastAPI:
    """`redis_client`, `catalog` e `promotions` injetados (testes) não são fechados aqui."""
    settings = settings or CartSettings()  # pyright: ignore[reportCallIssue]
    configure_logging(settings.service_name, settings.log_level)
    owned: list[Callable[[], Awaitable[None]]] = []

    redis = redis_client
    if redis is None:
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        owned.append(redis.aclose)

    if catalog is None or promotions is None:
        token_http = make_http_client("", UPSTREAM_TIMEOUT_S)
        tokens = ServiceTokenProvider(
            settings.identity_token_url,
            settings.client_id,
            settings.client_secret,
            http=token_http,
        )
        owned += [tokens.aclose, token_http.aclose]
        if catalog is None:
            catalog_http = make_http_client(settings.catalog_url, UPSTREAM_TIMEOUT_S)
            owned.append(catalog_http.aclose)
            catalog = CatalogClient(settings.catalog_url, tokens, catalog_http, UPSTREAM_TIMEOUT_S)
        if promotions is None:
            promotions_http = make_http_client(settings.promotions_url, UPSTREAM_TIMEOUT_S)
            owned.append(promotions_http.aclose)
            promotions = PromotionsClient(
                settings.promotions_url, tokens, promotions_http, UPSTREAM_TIMEOUT_S
            )

    async def ready_check() -> bool:
        return bool(await redis.ping())

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            for close in reversed(owned):
                await close()

    app = FastAPI(title="KatoShop cart", lifespan=lifespan)
    app.state.settings = settings
    app.state.redis = redis
    app.state.cart_repository = RedisCartRepository(redis, guest_ttl_s=settings.guest_ttl_s)
    app.state.catalog = catalog
    app.state.promotions = promotions
    app.state.token_verifier = TokenVerifier(JwksKeyProvider(settings.jwks_url))
    install_problem_handlers(app)
    install_cart_error_handler(app)
    configure_observability(app, settings)
    app.include_router(health_router(ready_check))
    app.include_router(cart_router)
    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn cart.main:app` carrega as settings do ambiente sob demanda.
    if name == "app":
        return create_app()
    raise AttributeError(name)
