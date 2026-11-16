import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx
import pytest

from cart.adapters.catalog_client import CatalogClient
from cart.adapters.promotions_client import CouponResult, PromotionsClient
from cart.domain.cart import CartError, CartItem
from ks_platform.service_tokens import ServiceTokenProvider

VID = "0192f0aa-0000-7000-8000-000000000001"
PID = "0192f0aa-0000-7000-8000-000000000002"

Handler = Callable[[httpx.Request], httpx.Response]


class TokenServer:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return httpx.Response(200, json={"access_token": f"tok{self.calls}", "expires_in": 300})


def _tokens(server: TokenServer | None = None) -> ServiceTokenProvider:
    http = httpx.AsyncClient(transport=httpx.MockTransport(server or TokenServer()))
    return ServiceTokenProvider("http://identity/token", "cart", "s", http=http)


def _http(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _variant(**over: object) -> dict[str, object]:
    data: dict[str, object] = {
        "variant_id": VID,
        "sku": "CAM-P-AZ",
        "product_id": PID,
        "product_slug": "camiseta",
        "product_status": "active",
        "name": "Camiseta",
        "color_code": "AZ",
        "color_name": "Azul",
        "size_code": "P",
        "unit_price_cents": 5990,
        "available": 7,
        "active": True,
        "image_url": None,
        "category_slug": "camisetas",
        "collection_slugs": ["verao"],
        "version": 4,
    }
    data.update(over)
    return data


def _catalog(handler: Handler, server: TokenServer | None = None) -> CatalogClient:
    return CatalogClient("http://catalog", _tokens(server), _http(handler))


async def test_variant_maps_snapshot_and_sends_bearer() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_variant())

    item = await _catalog(handler).variant(VID)
    assert item is not None
    assert seen[0].url.path == f"/v1/internal/variants/{VID}"
    assert seen[0].headers["authorization"] == "Bearer tok1"
    assert (item.variant_id, item.product_id, item.name) == (VID, PID, "Camiseta")
    assert (item.size_code, item.color_code, item.color_name) == ("P", "AZ", "Azul")
    assert (item.unit_price_cents, item.available, item.variant_version) == (5990, 7, 4)
    assert (item.category_slug, item.collection_slugs) == ("camisetas", ["verao"])
    assert (item.quantity, item.unavailable, item.archived) == (0, False, False)


@pytest.mark.parametrize(
    ("over", "unavailable", "archived"),
    [
        ({"active": False}, True, False),
        ({"available": 0}, True, False),
        ({"product_status": "draft"}, True, False),
        ({"product_status": "archived"}, True, True),
    ],
)
async def test_variant_unavailable_and_archived_flags(
    over: dict[str, object], unavailable: bool, archived: bool
) -> None:
    item = await _catalog(lambda r: httpx.Response(200, json=_variant(**over))).variant(VID)
    assert item is not None
    assert (item.unavailable, item.archived) == (unavailable, archived)


async def test_variant_404_is_none() -> None:
    assert await _catalog(lambda r: httpx.Response(404)).variant(VID) is None


async def test_variant_422_is_item_not_found() -> None:
    with pytest.raises(CartError) as exc:
        await _catalog(lambda r: httpx.Response(422)).variant("x")
    assert (exc.value.code, exc.value.extra) == ("cart.item.not_found", {"status": 404})


@pytest.mark.parametrize("status", [500, 503, 403, 400])
async def test_variant_other_errors_are_unavailable(status: int) -> None:
    with pytest.raises(CartError) as exc:
        await _catalog(lambda r: httpx.Response(status)).variant(VID)
    assert (exc.value.code, exc.value.extra) == ("cart.catalog.unavailable", {"status": 503})


async def test_variant_timeout_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(CartError) as exc:
        await _catalog(handler).variant(VID)
    assert exc.value.code == "cart.catalog.unavailable"


async def test_variant_token_failure_is_unavailable() -> None:
    tokens = ServiceTokenProvider(
        "http://identity/token", "cart", "s", http=_http(lambda r: httpx.Response(503))
    )
    client = CatalogClient("http://catalog", tokens, _http(lambda r: httpx.Response(200)))
    with pytest.raises(CartError) as exc:
        await client.variant(VID)
    assert exc.value.code == "cart.catalog.unavailable"


async def test_variant_401_invalidates_token_and_retries_once() -> None:
    auth: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth.append(request.headers["authorization"])
        if len(auth) == 1:
            return httpx.Response(401)
        return httpx.Response(200, json=_variant())

    server = TokenServer()
    assert await _catalog(handler, server).variant(VID) is not None
    assert auth == ["Bearer tok1", "Bearer tok2"]
    assert server.calls == 2


async def test_variant_second_401_is_unavailable() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    with pytest.raises(CartError) as exc:
        await _catalog(handler).variant(VID)
    assert exc.value.code == "cart.catalog.unavailable"
    assert calls == 2


def _item(variant_id: str = VID, **over: Any) -> CartItem:
    base = CartItem(
        variant_id=variant_id,
        product_id=PID,
        product_slug="camiseta",
        name="Camiseta",
        color_code="AZ",
        color_name="Azul",
        size_code="P",
        image_url=None,
        unit_price_cents=5990,
        available=7,
        category_slug="camisetas",
        collection_slugs=["verao"],
        quantity=2,
        variant_version=4,
    )
    return replace(base, **over)


def _promotions(handler: Handler) -> PromotionsClient:
    return PromotionsClient("http://promotions", _tokens(), _http(handler))


_OK: dict[str, Any] = {
    "valid": True,
    "code": "BEMVINDO10",
    "discount_cents": 1198,
    "per_item": [{"variant_id": VID, "discount_cents": 1198}],
    "reason": None,
    "min_order_cents": None,
}


async def test_evaluate_sends_only_available_items_and_maps_result() -> None:
    other = "0192f0aa-0000-7000-8000-000000000009"
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_OK)

    result = await _promotions(handler).evaluate(
        "BEMVINDO10", "cust-1", [_item(), _item(other, unavailable=True)]
    )
    assert result == CouponResult(
        valid=True, discount_cents=1198, per_item={VID: 1198}, reason=None, min_order_cents=None
    )
    request = seen[0]
    assert (request.method, request.url.path) == ("POST", "/v1/promotions/evaluate")
    assert request.headers["authorization"] == "Bearer tok1"
    assert json.loads(request.content) == {
        "code": "BEMVINDO10",
        "customer_id": "cust-1",
        "items": [
            {
                "variant_id": VID,
                "quantity": 2,
                "unit_price_cents": 5990,
                "category_slug": "camisetas",
                "collection_slugs": ["verao"],
            }
        ],
    }


async def test_evaluate_without_available_items_does_not_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("não deve chamar")

    result = await _promotions(handler).evaluate("X", None, [_item(unavailable=True)])
    assert result == CouponResult(valid=False, reason="promotions.coupon.no_eligible_items")


async def test_evaluate_invalid_coupon_passes_reason_through() -> None:
    body = {**_OK, "valid": False, "discount_cents": 0, "per_item": [], "reason": "x.y"}
    body["min_order_cents"] = 10000
    result = await _promotions(lambda r: httpx.Response(200, json=body)).evaluate(
        "BEMVINDO10", None, [_item()]
    )
    assert result == CouponResult(valid=False, reason="x.y", min_order_cents=10000)


async def test_evaluate_timeout_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    result = await _promotions(handler).evaluate("X", None, [_item()])
    assert result == CouponResult(valid=False, reason="promotions.unavailable")


@pytest.mark.parametrize("status", [500, 502, 422])
async def test_evaluate_bad_status_is_unavailable(status: int) -> None:
    result = await _promotions(lambda r: httpx.Response(status)).evaluate("X", None, [_item()])
    assert result.reason == "promotions.unavailable"
    assert result.valid is False


async def test_evaluate_401_retries_once_then_unavailable() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    result = await _promotions(handler).evaluate("X", None, [_item()])
    assert result.reason == "promotions.unavailable"
    assert calls == 2
