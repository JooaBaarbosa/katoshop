from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from cart.adapters.catalog_client import CatalogClient
from cart.adapters.consumer import CatalogEventsConsumer
from cart.adapters.promotions_client import PromotionsClient
from cart.adapters.redis_repo import RedisCartRepository
from cart.api.errors import install_cart_error_handlers
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


def _open_upstreams(
    app: FastAPI,
    settings: CartSettings,
    stack: AsyncExitStack,
    catalog: CatalogPort | None,
    promotions: PromotionsPort | None,
) -> None:
    """Cria (no lifespan) os clientes que não foram injetados e registra o fechamento."""
    if catalog is None or promotions is None:
        token_http = make_http_client("", UPSTREAM_TIMEOUT_S)
        stack.push_async_callback(token_http.aclose)
        tokens = ServiceTokenProvider(
            settings.identity_token_url,
            settings.client_id,
            settings.client_secret,
            http=token_http,
        )
        stack.push_async_callback(tokens.aclose)
        if catalog is None:
            catalog_http = make_http_client(settings.catalog_url, UPSTREAM_TIMEOUT_S)
            stack.push_async_callback(catalog_http.aclose)
            catalog = CatalogClient(settings.catalog_url, tokens, catalog_http, UPSTREAM_TIMEOUT_S)
        if promotions is None:
            promotions_http = make_http_client(settings.promotions_url, UPSTREAM_TIMEOUT_S)
            stack.push_async_callback(promotions_http.aclose)
            promotions = PromotionsClient(
                settings.promotions_url, tokens, promotions_http, UPSTREAM_TIMEOUT_S
            )
    app.state.catalog = catalog
    app.state.promotions = promotions


def create_app(
    settings: CartSettings | None = None,
    redis_client: Redis | None = None,
    *,
    catalog: CatalogPort | None = None,
    promotions: PromotionsPort | None = None,
) -> FastAPI:
    """Os recursos próprios (Redis, clientes http, token) nascem e morrem no lifespan; os
    injetados (`redis_client`, `catalog`, `promotions`, para testes) não são fechados aqui."""
    settings = settings or CartSettings()  # pyright: ignore[reportCallIssue]
    configure_logging(settings.service_name, settings.log_level)

    async def ready_check() -> bool:
        redis: Redis = app.state.redis
        return bool(await redis.ping())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # AsyncExitStack: uma falha ao fechar um recurso não impede o fechamento dos outros.
        async with AsyncExitStack() as stack:
            redis = redis_client
            if redis is None:
                redis = Redis.from_url(
                    settings.redis_url, socket_connect_timeout=2, socket_timeout=2
                )
                stack.push_async_callback(redis.aclose)
            app.state.redis = redis
            repo = RedisCartRepository(redis, guest_ttl_s=settings.guest_ttl_s)
            app.state.cart_repository = repo
            _open_upstreams(app, settings, stack, catalog, promotions)
            if settings.amqp_url:
                # Sobe em segundo plano: broker fora não impede o cart de subir nem afeta a
                # prontidão (que depende só do Redis). Registrado depois do Redis, então o
                # desligamento para de consumir antes de fechar o Redis.
                consumer = CatalogEventsConsumer(settings.amqp_url, repo)
                consumer.start()
                stack.push_async_callback(consumer.stop)
            yield

    app = FastAPI(title="KatoShop cart", lifespan=lifespan)
    app.state.settings = settings
    app.state.token_verifier = TokenVerifier(JwksKeyProvider(settings.jwks_url))
    install_problem_handlers(app)
    install_cart_error_handlers(app)
    configure_observability(app, settings)
    app.include_router(health_router(ready_check))
    app.include_router(cart_router)
    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn cart.main:app` carrega as settings do ambiente sob demanda.
    if name == "app":
        return create_app()
    raise AttributeError(name)
