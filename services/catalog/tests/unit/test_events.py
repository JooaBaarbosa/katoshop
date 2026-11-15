import uuid
from dataclasses import replace
from datetime import UTC, datetime

from catalog.application.events import (
    EVENTS_EXCHANGE,
    PRICE_CHANGED,
    PRODUCT_ARCHIVED,
    STOCK_CHANGED,
    price_changed,
    product_archived,
    stock_changed,
)
from catalog.application.ports import CategoryRecord, ProductRecord, VariantRecord

PRODUCT_ID = uuid.uuid7()


def _variant(**overrides: object) -> VariantRecord:
    base = VariantRecord(
        id=uuid.uuid7(),
        product_id=PRODUCT_ID,
        sku="MOL-PRT-M",
        color_code="PRT",
        size_code="M",
        price_cents=None,
        stock_on_hand=10,
        stock_reserved=3,
        version=4,
        active=True,
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def _product(variants: list[VariantRecord]) -> ProductRecord:
    now = datetime.now(UTC)
    return ProductRecord(
        id=PRODUCT_ID,
        slug="moletom",
        name="Moletom",
        description=None,
        category=CategoryRecord(uuid.uuid7(), "moletons", "Moletons", None, 0),
        status="archived",
        base_price_cents=24900,
        min_price_cents=24900,
        attributes={},
        version=3,
        published_at=None,
        created_at=now,
        updated_at=now,
        variants=variants,
        images=[],
    )


def test_exchange_and_type_names() -> None:
    assert EVENTS_EXCHANGE == "catalog.events"
    assert PRICE_CHANGED == "catalog.variant.price_changed.v1"
    assert STOCK_CHANGED == "catalog.variant.stock_changed.v1"
    assert PRODUCT_ARCHIVED == "catalog.product.archived.v1"


def test_price_changed_payload() -> None:
    variant = _variant()
    event = price_changed(variant, 24900, 19900)
    assert event.type == PRICE_CHANGED
    assert event.version == 1
    assert event.producer == "catalog"
    assert event.data == {
        "variant_id": str(variant.id),
        "sku": "MOL-PRT-M",
        "product_id": str(PRODUCT_ID),
        "old_price_cents": 24900,
        "new_price_cents": 19900,
        "version": 4,
    }


def test_stock_changed_payload_uses_available() -> None:
    variant = _variant()
    event = stock_changed(variant)
    assert event.type == STOCK_CHANGED
    assert event.producer == "catalog"
    assert event.data == {
        "variant_id": str(variant.id),
        "sku": "MOL-PRT-M",
        "available": 7,
        "version": 4,
    }


def test_stock_changed_is_zero_for_inactive_variant() -> None:
    event = stock_changed(_variant(active=False))
    assert event.data["available"] == 0


def test_product_archived_payload_lists_all_variants() -> None:
    variants = [_variant(), _variant(sku="MOL-PRT-G", active=False)]
    event = product_archived(_product(variants))
    assert event.type == PRODUCT_ARCHIVED
    assert event.producer == "catalog"
    assert event.data == {
        "product_id": str(PRODUCT_ID),
        "variant_ids": [str(v.id) for v in variants],
    }


def test_events_roundtrip_as_json() -> None:
    event = price_changed(_variant(), 100, 200)
    assert type(event).from_json(event.to_json()) == event
