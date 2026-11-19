"""`CartError` do domínio e da aplicação em problem+json, com os campos extras (`max`, `reason`)."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry import trace

from cart.domain.cart import CartError
from ks_platform.errors import PROBLEM_MEDIA_TYPE

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


def install_cart_error_handler(app: FastAPI) -> None:
    @app.exception_handler(CartError)
    async def _cart_error(_: Request, exc: CartError) -> JSONResponse:
        default_status, title = _STATUS.get(exc.code, (422, "Operação inválida"))
        extra = dict(exc.extra)
        status = extra.pop("status", default_status)
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
