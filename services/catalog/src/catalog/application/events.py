"""Eventos de domínio do catalog (spec da fatia 2, §3.4). Vão para a outbox na transação
da escrita e o relay os publica no exchange `catalog.events` com routing key = tipo."""

from typing import Any

from opentelemetry import trace

from catalog.application.ports import ProductRecord, VariantRecord
from ks_platform.events import Envelope, new_event

EVENTS_EXCHANGE = "catalog.events"
PRODUCER = "catalog"

PRICE_CHANGED = "catalog.variant.price_changed.v1"
STOCK_CHANGED = "catalog.variant.stock_changed.v1"
PRODUCT_ARCHIVED = "catalog.product.archived.v1"


def correlation_id() -> str | None:
    """Trace id (32 hex) da requisição corrente; liga o evento ao trace que o originou."""
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else None


def _event(type_: str, data: dict[str, Any]) -> Envelope:
    return new_event(type_, PRODUCER, data, correlation_id=correlation_id())


def available(variant: VariantRecord) -> int:
    """Disponível para venda; variante inativa não vende nada."""
    if not variant.active:
        return 0
    return max(variant.stock_on_hand - variant.stock_reserved, 0)


def price_changed(variant: VariantRecord, old_cents: int, new_cents: int) -> Envelope:
    """`variant` já com a versão de depois da mudança."""
    return _event(
        PRICE_CHANGED,
        {
            "variant_id": str(variant.id),
            "sku": variant.sku,
            "product_id": str(variant.product_id),
            "old_price_cents": old_cents,
            "new_price_cents": new_cents,
            "version": variant.version,
        },
    )


def stock_changed(variant: VariantRecord) -> Envelope:
    """`variant` já com a versão de depois da mudança."""
    return _event(
        STOCK_CHANGED,
        {
            "variant_id": str(variant.id),
            "sku": variant.sku,
            "available": available(variant),
            "version": variant.version,
        },
    )


def product_archived(product: ProductRecord) -> Envelope:
    return _event(
        PRODUCT_ARCHIVED,
        {
            "product_id": str(product.id),
            "variant_ids": [str(v.id) for v in product.variants],
        },
    )
