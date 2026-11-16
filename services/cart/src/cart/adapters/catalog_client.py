from typing import Any

import httpx
import structlog

from cart.adapters._service_call import ServiceUnavailableError, call_service
from cart.domain.cart import CartError, CartItem
from ks_platform.service_tokens import ServiceTokenProvider

log = structlog.get_logger()


def _snapshot(data: dict[str, Any]) -> CartItem:
    product_status: str = data["product_status"]
    return CartItem(
        variant_id=str(data["variant_id"]),
        product_id=str(data["product_id"]),
        product_slug=data["product_slug"],
        name=data["name"],
        color_code=data["color_code"],
        color_name=data["color_name"],
        size_code=data["size_code"],
        image_url=data["image_url"],
        unit_price_cents=data["unit_price_cents"],
        available=data["available"],
        category_slug=data["category_slug"],
        collection_slugs=list(data["collection_slugs"]),
        quantity=0,
        variant_version=data["version"],
        unavailable=(not data["active"] or product_status != "active" or data["available"] == 0),
        archived=product_status == "archived",
    )


class CatalogClient:
    def __init__(
        self, base_url: str, tokens: ServiceTokenProvider, http: httpx.AsyncClient
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._tokens = tokens
        self._http = http

    async def variant(self, variant_id: str) -> CartItem | None:
        """Snapshot da variante (quantity=0); `None` se não existe."""
        url = f"{self._base_url}/v1/internal/variants/{variant_id}"
        try:
            response = await call_service(self._http, self._tokens, "GET", url, target="catalog")
        except ServiceUnavailableError as exc:
            raise CartError("cart.catalog.unavailable", status=503) from exc
        status = response.status_code
        if status == 404:
            return None
        if status == 422:
            raise CartError("cart.item.not_found", status=404)
        if status != 200:
            log.warning("catalog.unexpected_status", status=status)
            raise CartError("cart.catalog.unavailable", status=503)
        try:
            return _snapshot(response.json())
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("catalog.invalid_body", error=type(exc).__name__)
            raise CartError("cart.catalog.unavailable", status=503) from exc
