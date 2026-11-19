"""`CartError` do domínio e da aplicação em problem+json, com os campos extras (`max`, `reason`)."""

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry import trace
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import OutOfMemoryError as RedisOutOfMemoryError
from redis.exceptions import TimeoutError as RedisTimeoutError
from starlette.responses import Response

from cart.domain.cart import CartError
from ks_platform.errors import PROBLEM_MEDIA_TYPE, ProblemError

log = structlog.get_logger()

_STATUS: dict[str, tuple[int, str]] = {
    "cart.cart.invalid_id": (422, "Identificador de carrinho inválido"),
    "cart.cart.not_found": (404, "Carrinho não encontrado"),
    "cart.cart.too_many_lines": (422, "Limite de itens no carrinho atingido"),
    "cart.cart.concurrent_update": (409, "Carrinho alterado ao mesmo tempo, tente de novo"),
    "cart.item.not_found": (404, "Item não encontrado"),
    "cart.item.unavailable": (422, "Item indisponível"),
    "cart.item.quantity_limit": (422, "Quantidade fora do limite"),
    "cart.item.quantity_exceeds_stock": (422, "Quantidade acima do estoque"),
    "cart.coupon.invalid": (422, "Cupom inválido"),
    "cart.catalog.unavailable": (503, "Catálogo indisponível"),
    "cart.promotions.unavailable": (503, "Não foi possível validar o cupom agora"),
}


def _trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


def install_cart_error_handlers(app: FastAPI) -> None:
    """Chame depois de `install_problem_handlers`: os casos sem extras reusam o handler dele."""

    async def as_problem(request: Request, problem: ProblemError) -> Response:
        handler = app.exception_handlers[ProblemError]
        return await handler(request, problem)  # pyright: ignore[reportGeneralTypeIssues]

    @app.exception_handler(CartError)
    async def _cart_error(request: Request, exc: CartError) -> Response:
        known = _STATUS.get(exc.code)
        if known is None:
            # Código sem mapeamento é bug, não erro do cliente.
            log.error("cart.unmapped_error", code=exc.code)
            return await as_problem(request, ProblemError(500, "internal.error", "Erro interno"))
        status, title = known
        extra = {k: v for k, v in exc.extra.items() if k != "status"}
        body: dict[str, object] = {
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": None,
            "code": exc.code,
            "trace_id": _trace_id(),
            **extra,
        }
        return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE)

    async def _storage_unavailable(request: Request, exc: Exception) -> Response:
        log.warning("cart.storage_unavailable", error=type(exc).__name__)
        problem = ProblemError(503, "cart.storage.unavailable", "Carrinho indisponível no momento")
        return await as_problem(request, problem)

    app.add_exception_handler(RedisConnectionError, _storage_unavailable)
    app.add_exception_handler(RedisTimeoutError, _storage_unavailable)
    # maxmemory sem chave com TTL a expulsar (S13): a escrita é recusada, o serviço segue de pé.
    app.add_exception_handler(RedisOutOfMemoryError, _storage_unavailable)
