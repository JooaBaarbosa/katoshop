from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from cart.adapters._service_call import (
    ServiceUnavailableError,
    bool_value,
    call_service,
    canonical_uuid,
    int_value,
)
from cart.domain.cart import CartItem
from ks_platform.service_tokens import ServiceTokenProvider

log = structlog.get_logger()


@dataclass(frozen=True)
class CouponResult:
    valid: bool
    discount_cents: int = 0
    # variant_id -> desconto da linha, em centavos.
    per_item: dict[str, int] = field(default_factory=dict)
    reason: str | None = None
    min_order_cents: int | None = None


def _unavailable() -> CouponResult:
    return CouponResult(valid=False, reason="promotions.unavailable")


class PromotionsClient:
    def __init__(
        self,
        base_url: str,
        tokens: ServiceTokenProvider,
        http: httpx.AsyncClient,
        timeout_s: float = 2.0,
    ) -> None:
        self._timeout_s = timeout_s
        self._base_url = base_url.rstrip("/")
        self._tokens = tokens
        self._http = http

    async def evaluate(
        self, code: str, customer_id: str | None, items: list[CartItem]
    ) -> CouponResult:
        """Avalia o cupom sobre os itens disponíveis; nunca levanta por falha do destino."""
        eligible = [i for i in items if not i.unavailable]
        if not eligible:
            return CouponResult(valid=False, reason="promotions.coupon.no_eligible_items")
        body: dict[str, Any] = {
            "code": code,
            "customer_id": customer_id,
            "items": [
                {
                    "variant_id": i.variant_id,
                    "quantity": i.quantity,
                    "unit_price_cents": i.unit_price_cents,
                    "category_slug": i.category_slug,
                    "collection_slugs": i.collection_slugs,
                }
                for i in eligible
            ],
        }
        try:
            response = await call_service(
                self._http,
                self._tokens,
                "POST",
                f"{self._base_url}/v1/promotions/evaluate",
                target="promotions",
                json=body,
                timeout_s=self._timeout_s,
            )
        except ServiceUnavailableError:
            return _unavailable()
        if response.status_code != 200:
            log.warning("promotions.unexpected_status", status=response.status_code)
            return _unavailable()
        try:
            data = response.json()
            reason = data["reason"]
            if reason is not None and not isinstance(reason, str):
                raise ValueError("reason inválido")
            min_order = data["min_order_cents"]
            if min_order is not None:
                min_order = int_value(min_order)
            return CouponResult(
                valid=bool_value(data["valid"]),
                discount_cents=int_value(data["discount_cents"]),
                # Mesma chave canônica (UUID minúsculo) que o carrinho usa para as variantes.
                per_item={
                    canonical_uuid(p["variant_id"]): int_value(p["discount_cents"])
                    for p in data["per_item"]
                },
                reason=reason,
                min_order_cents=min_order,
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            log.warning("promotions.invalid_body", error=type(exc).__name__)
            return _unavailable()
