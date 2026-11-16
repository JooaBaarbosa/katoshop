import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

type Json = dict[str, Any]

URL = "/v1/promotions/evaluate"
VARIANT_A = "018f0000-0000-7000-8000-00000000000a"
VARIANT_B = "018f0000-0000-7000-8000-00000000000b"


def item(variant_id: str, price: int, qty: int = 1, category: str = "moletons") -> Json:
    return {
        "variant_id": variant_id,
        "unit_price_cents": price,
        "quantity": qty,
        "category_slug": category,
        "collection_slugs": [],
    }


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


type MakeCoupon = Callable[..., Awaitable[Json]]


async def _evaluate(
    client: httpx.AsyncClient, token: str, code: str, items: list[Json], **extra: Any
) -> httpx.Response:
    return await client.post(
        URL, json={"code": code, "items": items, **extra}, headers=bearer(token)
    )


@pytest.fixture
def make_coupon(
    client: httpx.AsyncClient, admin_token: str, new_code: Callable[[str], str]
) -> MakeCoupon:
    async def make(**overrides: Any) -> Json:
        response = await client.post(
            "/v1/admin/coupons",
            json={"code": new_code("EV"), "kind": "percent", "value": 10, **overrides},
            headers=bearer(admin_token),
        )
        assert response.status_code == 201, response.text
        return response.json()

    return make


async def test_evaluate_valid_coupon(
    client: httpx.AsyncClient, service_token: str, make_coupon: MakeCoupon
) -> None:
    coupon = await make_coupon()
    response = await _evaluate(
        client,
        service_token,
        coupon["code"],
        [item(VARIANT_A, 10000, 2), item(VARIANT_B, 5000)],
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "valid": True,
        "code": coupon["code"],
        "discount_cents": 2500,
        "per_item": [
            {"variant_id": VARIANT_A, "discount_cents": 2000},
            {"variant_id": VARIANT_B, "discount_cents": 500},
        ],
        "reason": None,
        "min_order_cents": None,
    }


async def test_evaluate_normalizes_code(
    client: httpx.AsyncClient, service_token: str, make_coupon: MakeCoupon
) -> None:
    coupon = await make_coupon()
    response = await _evaluate(
        client, service_token, f"  {coupon['code'].lower()} ", [item(VARIANT_A, 1000)]
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert response.json()["code"] == coupon["code"]


async def test_evaluate_unknown_or_malformed_code_is_not_found(
    client: httpx.AsyncClient, service_token: str, new_code: Callable[[str], str]
) -> None:
    for code in [new_code("NOPE"), "a b", "CÓDIGO", "x" * 100, ""]:
        response = await _evaluate(client, service_token, code, [item(VARIANT_A, 1000)])
        assert response.status_code == 200, code
        data = response.json()
        assert data["valid"] is False
        assert data["reason"] == "promotions.coupon.not_found"
        assert data["discount_cents"] == 0
        assert data["per_item"] == []


async def test_evaluate_reason_with_min_order(
    client: httpx.AsyncClient, service_token: str, make_coupon: MakeCoupon
) -> None:
    coupon = await make_coupon(min_order_cents=20000)
    response = await _evaluate(client, service_token, coupon["code"], [item(VARIANT_A, 1000)])
    data = response.json()
    assert data["valid"] is False
    assert data["reason"] == "promotions.coupon.min_order_not_met"
    assert data["min_order_cents"] == 20000


async def test_evaluate_inactive(
    client: httpx.AsyncClient, service_token: str, make_coupon: MakeCoupon
) -> None:
    coupon = await make_coupon(active=False)
    response = await _evaluate(client, service_token, coupon["code"], [item(VARIANT_A, 1000)])
    assert response.json()["reason"] == "promotions.coupon.inactive"


async def test_evaluate_total_limit_comes_from_redemptions(
    client: httpx.AsyncClient,
    service_token: str,
    make_coupon: MakeCoupon,
    redeem: Callable[..., Awaitable[None]],
) -> None:
    coupon = await make_coupon(max_uses_total=1)
    first = await _evaluate(client, service_token, coupon["code"], [item(VARIANT_A, 1000)])
    assert first.json()["valid"] is True
    await redeem(coupon["id"])
    second = await _evaluate(client, service_token, coupon["code"], [item(VARIANT_A, 1000)])
    assert second.json()["reason"] == "promotions.coupon.usage_limit_reached"


async def test_evaluate_per_customer_limit(
    client: httpx.AsyncClient,
    service_token: str,
    make_coupon: MakeCoupon,
    redeem: Callable[..., Awaitable[None]],
) -> None:
    coupon = await make_coupon(max_uses_per_customer=1)
    items = [item(VARIANT_A, 1000)]
    guest = await _evaluate(client, service_token, coupon["code"], items)
    assert guest.json()["reason"] == "promotions.coupon.login_required"
    customer = uuid.uuid4()
    fresh = await _evaluate(client, service_token, coupon["code"], items, customer_id=str(customer))
    assert fresh.json()["valid"] is True
    await redeem(coupon["id"], customer)
    used = await _evaluate(client, service_token, coupon["code"], items, customer_id=str(customer))
    assert used.json()["reason"] == "promotions.coupon.customer_limit_reached"
    other = await _evaluate(
        client, service_token, coupon["code"], items, customer_id=str(uuid.uuid4())
    )
    assert other.json()["valid"] is True


async def test_evaluate_requires_service_token(
    client: httpx.AsyncClient, admin_token: str, customer_token: str
) -> None:
    payload = {"code": "ABC", "items": [item(VARIANT_A, 1000)]}
    assert (await client.post(URL, json=payload)).status_code == 401
    assert (await client.post(URL, json=payload, headers=bearer(admin_token))).status_code == 403
    assert (await client.post(URL, json=payload, headers=bearer(customer_token))).status_code == 403


async def test_evaluate_rejects_bad_items(client: httpx.AsyncClient, service_token: str) -> None:
    empty = await _evaluate(client, service_token, "ABC", [])
    assert empty.status_code == 422
    assert empty.json()["code"] == "request.validation"
    assert "body.items" in empty.json()["errors"]
    too_many = await _evaluate(
        client, service_token, "ABC", [item(str(uuid.uuid4()), 100) for _ in range(51)]
    )
    assert too_many.status_code == 422
    zero_qty = await _evaluate(client, service_token, "ABC", [item(VARIANT_A, 100, 0)])
    assert zero_qty.status_code == 422


async def test_evaluate_rejects_duplicate_variant_ids(
    client: httpx.AsyncClient, service_token: str
) -> None:
    response = await _evaluate(
        client, service_token, "ABC", [item(VARIANT_A, 100), item(VARIANT_A, 200)]
    )
    assert response.status_code == 422
    assert response.json()["code"] == "request.validation"
    assert "body.items" in response.json()["errors"]
