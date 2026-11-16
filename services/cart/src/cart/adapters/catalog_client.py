from typing import Any

import httpx
import structlog

from cart.adapters._service_call import (
    ServiceUnavailableError,
    bool_value,
    call_service,
    canonical_uuid,
    int_value,
    str_value,
)
from cart.domain.cart import CartError, CartItem
from ks_platform.service_tokens import ServiceTokenProvider

log = structlog.get_logger()


def _snapshot(data: dict[str, Any]) -> CartItem:
    product_status = str_value(data["product_status"])
    active = bool_value(data["active"])
    available = int_value(data["available"])
    image_url = data["image_url"]
    if image_url is not None:
        image_url = str_value(image_url)
    collections = data["collection_slugs"]
    if not isinstance(collections, list):
        raise ValueError("collection_slugs inválido")
    return CartItem(
        variant_id=canonical_uuid(data["variant_id"]),
        product_id=canonical_uuid(data["product_id"]),
        product_slug=str_value(data["product_slug"]),
        name=str_value(data["name"]),
        color_code=str_value(data["color_code"]),
        color_name=str_value(data["color_name"]),
        size_code=str_value(data["size_code"]),
        image_url=image_url,
        unit_price_cents=int_value(data["unit_price_cents"]),
        available=available,
        category_slug=str_value(data["category_slug"]),
        collection_slugs=[str_value(slug) for slug in collections],
        quantity=0,
        variant_version=int_value(data["version"]),
        unavailable=(not active or product_status != "active" or available == 0),
        archived=product_status == "archived",
    )


class CatalogClient:
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

    async def variant(self, variant_id: str) -> CartItem | None:
        """Snapshot da variante (quantity=0); `None` se não existe."""
        try:
            canonical = canonical_uuid(variant_id)
        except ValueError as exc:
            raise CartError("cart.item.not_found", status=404) from exc
        url = f"{self._base_url}/v1/internal/variants/{canonical}"
        try:
            response = await call_service(
                self._http, self._tokens, "GET", url, target="catalog", timeout_s=self._timeout_s
            )
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
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            log.warning("catalog.invalid_body", error=type(exc).__name__)
            raise CartError("cart.catalog.unavailable", status=503) from exc
