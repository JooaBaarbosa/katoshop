import asyncio
import json
import time
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
        price_version=4,
        stock_version=4,
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


async def test_evaluate_read_budget_degrades_when_promotions_is_slow() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1.5)
        return httpx.Response(200, json=_OK)

    client = PromotionsClient(
        "http://promotions", _tokens(), httpx.AsyncClient(transport=httpx.MockTransport(slow))
    )
    started = time.monotonic()
    result = await client.evaluate("BEMVINDO10", None, [_item()], read=True)
    assert result == CouponResult(valid=False, reason="promotions.unavailable")
    assert time.monotonic() - started < 1.2


async def test_evaluate_read_budget_includes_token_issuance() -> None:
    async def slow_identity(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1.5)
        return httpx.Response(200, json={"access_token": "t", "expires_in": 300})

    tokens = ServiceTokenProvider(
        "http://identity/token",
        "cart",
        "s",
        http=httpx.AsyncClient(transport=httpx.MockTransport(slow_identity)),
    )
    client = PromotionsClient("http://promotions", tokens, _http(lambda r: httpx.Response(200)))
    started = time.monotonic()
    result = await client.evaluate("BEMVINDO10", None, [_item()], read=True)
    assert result.reason == "promotions.unavailable"
    assert time.monotonic() - started < 1.2


async def test_evaluate_write_budget_waits_for_slow_promotions() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1.2)
        return httpx.Response(200, json=_OK)

    result = await PromotionsClient(
        "http://promotions", _tokens(), httpx.AsyncClient(transport=httpx.MockTransport(slow))
    ).evaluate("BEMVINDO10", None, [_item()])
    assert result.valid is True


@pytest.mark.parametrize(("read", "expected_calls"), [(True, 1), (False, 2)])
async def test_evaluate_401_retry_only_outside_read_budget(read: bool, expected_calls: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    result = await _promotions(handler).evaluate("BEMVINDO10", None, [_item()], read=read)
    assert result.reason == "promotions.unavailable"
    assert calls == expected_calls


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


@pytest.mark.parametrize(
    "bad", ["../x", "abc?a=b", "a/b", "id\x00x", "id\nx", "", " " + VID + "/.."]
)
async def test_variant_invalid_id_is_not_found_without_calling(bad: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("não deve chamar")

    with pytest.raises(CartError) as exc:
        await _catalog(handler).variant(bad)
    assert (exc.value.code, exc.value.extra) == ("cart.item.not_found", {"status": 404})


async def test_variant_uses_canonical_lowercase_id_in_url() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_variant())

    await _catalog(handler).variant(VID.upper())
    assert seen[0].url.path == f"/v1/internal/variants/{VID}"


async def test_catalog_request_carries_timeout() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_variant())

    await _catalog(handler).variant(VID)
    assert seen[0].extensions["timeout"] == {"connect": 2.0, "read": 2.0, "write": 2.0, "pool": 2.0}


async def test_promotions_request_carries_timeout() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_OK)

    client = PromotionsClient("http://promotions", _tokens(), _http(handler), timeout_s=1.5)
    await client.evaluate("X", None, [_item()])
    assert seen[0].extensions["timeout"]["read"] == 1.5


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>nope</html>"),
        httpx.Response(200, json=[1, 2]),
        httpx.Response(200, json=_variant(unit_price_cents="59")),
        httpx.Response(200, json=_variant(unit_price_cents=True)),
        httpx.Response(200, json=_variant(available="7")),
        httpx.Response(200, json=_variant(active="yes")),
        httpx.Response(200, json=_variant(collection_slugs="verao")),
        httpx.Response(200, json=_variant(variant_id="nao-uuid")),
        httpx.Response(200, json=_variant(version=None)),
    ],
)
async def test_variant_malformed_body_is_unavailable(response: httpx.Response) -> None:
    with pytest.raises(CartError) as exc:
        await _catalog(lambda r: response).variant(VID)
    assert exc.value.code == "cart.catalog.unavailable"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>nope</html>"),
        httpx.Response(200, json=[1]),
        httpx.Response(200, json={**_OK, "valid": "true"}),
        httpx.Response(200, json={**_OK, "discount_cents": "10"}),
        httpx.Response(200, json={**_OK, "discount_cents": True}),
        httpx.Response(200, json={**_OK, "per_item": [{"variant_id": VID}]}),
        httpx.Response(200, json={**_OK, "per_item": [{"variant_id": "x", "discount_cents": 1}]}),
        httpx.Response(200, json={**_OK, "per_item": [1]}),
        httpx.Response(200, json={**_OK, "per_item": None}),
        httpx.Response(200, json={**_OK, "reason": 5}),
        httpx.Response(200, json={**_OK, "min_order_cents": "1"}),
    ],
)
async def test_evaluate_malformed_body_is_unavailable(response: httpx.Response) -> None:
    result = await _promotions(lambda r: response).evaluate("X", None, [_item()])
    assert result == CouponResult(valid=False, reason="promotions.unavailable")


async def test_evaluate_per_item_keys_are_canonical_lowercase() -> None:
    body = {**_OK, "per_item": [{"variant_id": VID.upper(), "discount_cents": 1198}]}
    result = await _promotions(lambda r: httpx.Response(200, json=body)).evaluate(
        "X", None, [_item()]
    )
    assert result.per_item == {VID: 1198}
