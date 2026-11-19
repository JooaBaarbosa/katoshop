import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

import httpx
import pytest
from fastapi import FastAPI
from redis.asyncio import Redis

from cart.adapters.promotions_client import CouponResult
from cart.domain.cart import CartError, CartItem
from cart.main import create_app
from cart.settings import CartSettings
from ks_platform.auth import JwksKeyProvider, TokenVerifier


class Signer(Protocol):
    """Contrato do fixture `signer` (conftest)."""

    @property
    def jwks(self) -> dict[str, Any]: ...

    def token(
        self,
        *,
        sub: uuid.UUID | str,
        aud: str,
        kind: str,
        roles: list[str] | None = None,
        expires_in: int = 900,
    ) -> str: ...


V1 = "0192f0aa-0000-7000-8000-000000000001"
V2 = "0192f0aa-0000-7000-8000-000000000002"
V3 = "0192f0aa-0000-7000-8000-000000000003"
PID = "0192f0aa-0000-7000-8000-0000000000ff"


def snapshot(variant_id: str, *, price: int = 5000, available: int = 10, **over: Any) -> CartItem:
    item = CartItem(
        variant_id=variant_id,
        product_id=PID,
        product_slug="camiseta",
        name="Camiseta",
        color_code="AZ",
        color_name="Azul",
        size_code="M",
        image_url=None,
        unit_price_cents=price,
        available=available,
        category_slug="camisetas",
        collection_slugs=["verao"],
        quantity=0,
        variant_version=1,
    )
    return replace(item, **over)


class FakeCatalog:
    def __init__(self) -> None:
        self.variants: dict[str, CartItem] = {}
        self.down = False

    async def variant(self, variant_id: str) -> CartItem | None:
        if self.down:
            raise CartError("cart.catalog.unavailable", status=503)
        found = self.variants.get(variant_id)
        return None if found is None else replace(found)


@dataclass
class FakePromotions:
    """BEMVINDO10: 10% por item. MIN500: exige R$ 500. Outros códigos: not_found."""

    down: bool = False
    calls: list[tuple[str, str | None]] = field(default_factory=list)
    invalid_now: set[str] = field(default_factory=set)

    async def evaluate(
        self, code: str, customer_id: str | None, items: list[CartItem]
    ) -> CouponResult:
        self.calls.append((code, customer_id))
        if self.down:
            return CouponResult(valid=False, reason="promotions.unavailable")
        eligible = [i for i in items if not i.unavailable]
        if code in self.invalid_now:
            return CouponResult(valid=False, reason="promotions.coupon.expired")
        if code == "BEMVINDO10":
            per_item = {i.variant_id: i.unit_price_cents * i.quantity // 10 for i in eligible}
            return CouponResult(
                valid=True, discount_cents=sum(per_item.values()), per_item=per_item
            )
        if code == "MIN500":
            subtotal = sum(i.unit_price_cents * i.quantity for i in eligible)
            if subtotal < 50000:
                return CouponResult(
                    valid=False, reason="promotions.coupon.min_order_not_met", min_order_cents=50000
                )
            return CouponResult(
                valid=True, discount_cents=1000, per_item={eligible[0].variant_id: 1000}
            )
        return CouponResult(valid=False, reason="promotions.coupon.not_found")


@pytest.fixture
async def redis(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def catalog() -> FakeCatalog:
    fake = FakeCatalog()
    for vid in (V1, V2, V3):
        fake.variants[vid] = snapshot(vid)
    return fake


@pytest.fixture
def promotions() -> FakePromotions:
    return FakePromotions()


@pytest.fixture
def app(
    redis_url: str,
    redis: Redis,
    catalog: FakeCatalog,
    promotions: FakePromotions,
    signer: Signer,
) -> FastAPI:
    settings = CartSettings(redis_url=redis_url, client_secret="x", guest_ttl_s=3600)  # noqa: S106
    application = create_app(settings, catalog=catalog, promotions=promotions)

    async def fetch(_url: str) -> dict[str, Any]:
        return signer.jwks

    application.state.token_verifier = TokenVerifier(
        JwksKeyProvider("http://test/jwks", fetch=fetch)
    )
    return application


@pytest.fixture
async def api(
    app: FastAPI,
    asgi_client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> AsyncIterator[httpx.AsyncClient]:
    async with asgi_client_factory(app) as http_client:
        yield http_client


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid7()


@pytest.fixture
def customer(signer: Signer, user_id: uuid.UUID) -> dict[str, str]:
    token = signer.token(sub=user_id, aud="storefront", kind="customer")
    return {"Authorization": f"Bearer {token}"}


def guest(cart_id: str) -> dict[str, str]:
    return {"X-Cart-Id": cart_id}


async def add(
    api: httpx.AsyncClient, variant_id: str, quantity: int, headers: dict[str, str] | None = None
) -> httpx.Response:
    return await api.post(
        "/v1/cart/items", json={"variant_id": variant_id, "quantity": quantity}, headers=headers
    )


async def new_guest_cart(api: httpx.AsyncClient, variant_id: str = V1, quantity: int = 1) -> str:
    resp = await add(api, variant_id, quantity)
    assert resp.status_code == 200, resp.text
    return resp.json()["cart_id"]


def item(body: dict[str, Any], variant_id: str) -> dict[str, Any]:
    return next(i for i in body["items"] if i["variant_id"] == variant_id)


EMPTY = {
    "cart_id": None,
    "items": [],
    "subtotal_cents": 0,
    "discount_cents": 0,
    "total_cents": 0,
    "coupon": None,
    "checkout_blocked": False,
}


# ------------------------------------------------------------------ visitante e itens


async def test_get_without_identity_returns_empty_cart(api: httpx.AsyncClient) -> None:
    resp = await api.get("/v1/cart")
    assert resp.status_code == 200
    assert resp.json() == EMPTY


async def test_guest_flow_creates_and_returns_cart_id(api: httpx.AsyncClient, redis: Redis) -> None:
    resp = await add(api, V1, 2)
    assert resp.status_code == 200
    body = resp.json()
    cart_id = body["cart_id"]
    assert uuid.UUID(cart_id).version == 4
    assert body["subtotal_cents"] == 10000
    assert body["total_cents"] == 10000
    line = item(body, V1)
    assert line["quantity"] == 2
    assert line["notice"] is None
    assert line["line_discount_cents"] == 0
    assert 0 < await redis.ttl(f"cart:{cart_id}") <= 3600

    again = await api.get("/v1/cart", headers=guest(cart_id))
    assert again.json()["cart_id"] == cart_id
    assert item(again.json(), V1)["quantity"] == 2


async def test_adding_same_sku_sums(api: httpx.AsyncClient) -> None:
    cart_id = await new_guest_cart(api, V1, 2)
    resp = await add(api, V1, 3, guest(cart_id))
    assert resp.status_code == 200
    assert resp.json()["cart_id"] == cart_id
    assert item(resp.json(), V1)["quantity"] == 5
    assert len(resp.json()["items"]) == 1


async def test_add_above_stock_422_with_max(api: httpx.AsyncClient, catalog: FakeCatalog) -> None:
    catalog.variants[V1] = snapshot(V1, available=3)
    resp = await add(api, V1, 4)
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["code"] == "cart.item.quantity_exceeds_stock"
    assert resp.json()["max"] == 3


async def test_failed_first_add_creates_no_cart(
    api: httpx.AsyncClient, catalog: FakeCatalog, redis: Redis
) -> None:
    catalog.variants[V1] = snapshot(V1, available=3)
    assert (await add(api, V1, 4)).status_code == 422
    assert await redis.keys("cart:*") == []


async def test_unknown_variant_404(api: httpx.AsyncClient) -> None:
    resp = await add(api, str(uuid.uuid7()), 1)
    assert resp.status_code == 404
    assert resp.json()["code"] == "cart.item.not_found"


async def test_malformed_variant_id_422(api: httpx.AsyncClient) -> None:
    resp = await add(api, "not-a-uuid", 1)
    assert resp.status_code == 422
    assert resp.json()["code"] == "request.validation"
    patch = await api.patch("/v1/cart/items/nope", json={"quantity": 1})
    assert patch.status_code == 422
    assert patch.json()["code"] == "request.validation"


async def test_variant_id_is_canonicalized(api: httpx.AsyncClient) -> None:
    resp = await add(api, V1.upper(), 1)
    assert resp.status_code == 200
    assert resp.json()["items"][0]["variant_id"] == V1


async def test_catalog_down_503(api: httpx.AsyncClient, catalog: FakeCatalog) -> None:
    catalog.down = True
    resp = await add(api, V1, 1)
    assert resp.status_code == 503
    assert resp.json()["code"] == "cart.catalog.unavailable"


async def test_patch_quantity_and_zero_removes(api: httpx.AsyncClient) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    await add(api, V2, 1, guest(cart_id))
    resp = await api.patch(f"/v1/cart/items/{V1}", json={"quantity": 4}, headers=guest(cart_id))
    assert resp.status_code == 200
    assert item(resp.json(), V1)["quantity"] == 4
    resp = await api.patch(f"/v1/cart/items/{V1}", json={"quantity": 0}, headers=guest(cart_id))
    assert [i["variant_id"] for i in resp.json()["items"]] == [V2]


async def test_patch_above_stock_422(api: httpx.AsyncClient) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    resp = await api.patch(f"/v1/cart/items/{V1}", json={"quantity": 11}, headers=guest(cart_id))
    assert resp.status_code == 422
    assert resp.json()["code"] == "cart.item.quantity_exceeds_stock"
    assert resp.json()["max"] == 10


async def test_patch_missing_item_404(api: httpx.AsyncClient) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    resp = await api.patch(f"/v1/cart/items/{V2}", json={"quantity": 1}, headers=guest(cart_id))
    assert resp.status_code == 404
    assert resp.json()["code"] == "cart.item.not_found"


async def test_delete_item(api: httpx.AsyncClient) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    resp = await api.delete(f"/v1/cart/items/{V1}", headers=guest(cart_id))
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["cart_id"] == cart_id


async def _mark(redis: Redis, cart_id: str, variant_id: str, **fields: Any) -> None:
    import json  # noqa: PLC0415

    key = f"cart:{cart_id}:items"
    data = json.loads(await redis.hget(key, variant_id))  # pyright: ignore[reportArgumentType, reportGeneralTypeIssues]
    data.update(fields)
    await redis.hset(key, variant_id, json.dumps(data))


async def test_delete_unavailable_items(api: httpx.AsyncClient, redis: Redis) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    await add(api, V2, 1, guest(cart_id))
    await _mark(redis, cart_id, V2, unavailable=True, notice={"code": "unavailable"})
    before = (await api.get("/v1/cart", headers=guest(cart_id))).json()
    assert before["checkout_blocked"] is True
    assert item(before, V2)["notice"]["code"] == "unavailable"
    assert item(before, V2)["unavailable"] is True
    assert before["subtotal_cents"] == 5000

    resp = await api.delete("/v1/cart/items/unavailable", headers=guest(cart_id))
    assert resp.status_code == 200
    assert [i["variant_id"] for i in resp.json()["items"]] == [V1]
    assert resp.json()["checkout_blocked"] is False


async def test_notices_ack_clears_notices(api: httpx.AsyncClient, redis: Redis) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    await add(api, V2, 1, guest(cart_id))
    await _mark(
        redis,
        cart_id,
        V1,
        notice={"code": "price_changed", "old_price_cents": 4000, "new_price_cents": 5000},
    )
    await _mark(redis, cart_id, V2, notice={"code": "quantity_reduced", "quantity": 1})
    before = (await api.get("/v1/cart", headers=guest(cart_id))).json()
    assert item(before, V1)["notice"] == {
        "code": "price_changed",
        "old_price_cents": 4000,
        "new_price_cents": 5000,
        "quantity": None,
    }

    resp = await api.post("/v1/cart/notices/ack", headers=guest(cart_id))
    assert resp.status_code == 200
    assert all(i["notice"] is None for i in resp.json()["items"])
    again = (await api.get("/v1/cart", headers=guest(cart_id))).json()
    assert all(i["notice"] is None for i in again["items"])


async def test_editing_line_clears_its_notice(api: httpx.AsyncClient, redis: Redis) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    await add(api, V2, 1, guest(cart_id))
    await _mark(redis, cart_id, V1, notice={"code": "quantity_reduced", "quantity": 1})
    await _mark(redis, cart_id, V2, notice={"code": "quantity_reduced", "quantity": 1})
    resp = await api.patch(f"/v1/cart/items/{V1}", json={"quantity": 2}, headers=guest(cart_id))
    assert item(resp.json(), V1)["notice"] is None
    assert item(resp.json(), V2)["notice"] is not None


# ------------------------------------------------------------------ X-Cart-Id (Review Focus 5)


async def test_unknown_guest_id_returns_empty_without_creating(
    api: httpx.AsyncClient, redis: Redis
) -> None:
    resp = await api.get("/v1/cart", headers=guest(str(uuid.uuid4())))
    assert resp.status_code == 200
    assert resp.json() == EMPTY
    assert await redis.keys("*") == []


async def test_unknown_guest_id_on_add_creates_fresh_cart(api: httpx.AsyncClient) -> None:
    unknown = str(uuid.uuid4())
    resp = await add(api, V1, 1, guest(unknown))
    assert resp.status_code == 200
    assert resp.json()["cart_id"] != unknown


async def test_user_cart_id_as_guest_header_treated_as_unknown(
    api: httpx.AsyncClient, redis: Redis, customer: dict[str, str]
) -> None:
    user_cart = (await add(api, V1, 1, customer)).json()["cart_id"]
    assert user_cart is not None
    resp = await api.get("/v1/cart", headers=guest(user_cart))
    assert resp.json() == EMPTY
    # Mesmo um carrinho de cliente com ID em formato v4 fica invisível para o visitante.
    forged = str(uuid.uuid4())
    await redis.hset(f"cart:{forged}", mapping={"owner": "user:someone", "version": 0})
    assert (await api.get("/v1/cart", headers=guest(forged))).json() == EMPTY
    resp = await api.delete(f"/v1/cart/items/{V1}", headers=guest(user_cart))
    assert resp.json() == EMPTY
    mine = (await api.get("/v1/cart", headers=customer)).json()
    assert item(mine, V1)["quantity"] == 1


async def test_malformed_cart_id_422(api: httpx.AsyncClient) -> None:
    for bad in ("abc", "", str(uuid.uuid4()).upper(), uuid.uuid4().hex, "x" * 36):
        resp = await api.get("/v1/cart", headers=guest(bad))
        assert resp.status_code == 422, bad
        assert resp.json()["code"] == "cart.cart.invalid_id"


async def test_non_v4_cart_id_treated_as_unknown(api: httpx.AsyncClient, redis: Redis) -> None:
    resp = await api.get("/v1/cart", headers=guest(str(uuid.uuid7())))
    assert resp.status_code == 200
    assert resp.json() == EMPTY
    assert await redis.keys("*") == []


async def test_token_ignores_cart_id_header(
    api: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    guest_cart = await new_guest_cart(api, V1, 3)
    resp = await api.get("/v1/cart", headers={**customer, **guest(guest_cart)})
    assert resp.json()["items"] == []
    assert resp.json()["cart_id"] != guest_cart


# ------------------------------------------------------------------ autenticação (Ruling S2)


async def test_invalid_token_401(api: httpx.AsyncClient) -> None:
    resp = await api.get("/v1/cart", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.invalid_token"


async def test_expired_token_401(api: httpx.AsyncClient, signer: Signer) -> None:
    token = signer.token(sub=uuid.uuid7(), aud="storefront", kind="customer", expires_in=-60)
    resp = await api.get("/v1/cart", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_wrong_audience_403(api: httpx.AsyncClient, signer: Signer) -> None:
    token = signer.token(sub=uuid.uuid7(), aud="admin", kind="staff", roles=["admin"])
    resp = await api.get("/v1/cart", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "auth.forbidden"


async def test_user_cart_persists_without_ttl(
    api: httpx.AsyncClient, customer: dict[str, str], redis: Redis
) -> None:
    resp = await add(api, V1, 2, customer)
    cart_id = resp.json()["cart_id"]
    assert await redis.ttl(f"cart:{cart_id}") == -1
    assert item((await api.get("/v1/cart", headers=customer)).json(), V1)["quantity"] == 2


# ------------------------------------------------------------------ cupom


async def test_put_valid_coupon_shows_in_total(api: httpx.AsyncClient) -> None:
    cart_id = await new_guest_cart(api, V1, 2)
    await add(api, V2, 1, guest(cart_id))
    resp = await api.put("/v1/cart/coupon", json={"code": "BEMVINDO10"}, headers=guest(cart_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["coupon"] == {
        "code": "BEMVINDO10",
        "valid": True,
        "reason": None,
        "min_order_cents": None,
    }
    assert body["subtotal_cents"] == 15000
    assert body["discount_cents"] == 1500
    assert body["total_cents"] == 13500
    assert item(body, V1)["line_discount_cents"] == 1000
    assert item(body, V2)["line_discount_cents"] == 500
    got = (await api.get("/v1/cart", headers=guest(cart_id))).json()
    assert got["total_cents"] == 13500


async def test_put_coupon_normalizes_code(
    api: httpx.AsyncClient, promotions: FakePromotions
) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    resp = await api.put("/v1/cart/coupon", json={"code": " bemvindo10 "}, headers=guest(cart_id))
    assert resp.status_code == 200
    assert resp.json()["coupon"]["code"] == "BEMVINDO10"
    assert promotions.calls[-1][0] == "BEMVINDO10"


@pytest.mark.parametrize("code", ["BEM VINDO", "ÇUPOM10", "AB", "X" * 33, "bem_vindo"])
async def test_put_malformed_coupon_422(
    api: httpx.AsyncClient, promotions: FakePromotions, code: str
) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    resp = await api.put("/v1/cart/coupon", json={"code": code}, headers=guest(cart_id))
    assert resp.status_code == 422
    assert resp.json()["code"] == "cart.coupon.invalid"
    assert resp.json()["reason"] == "promotions.coupon.not_found"
    assert promotions.calls == []


async def test_put_invalid_coupon_422_with_reason_and_not_stored(api: httpx.AsyncClient) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    resp = await api.put("/v1/cart/coupon", json={"code": "MIN500"}, headers=guest(cart_id))
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "cart.coupon.invalid"
    assert body["reason"] == "promotions.coupon.min_order_not_met"
    assert body["min_order_cents"] == 50000
    assert (await api.get("/v1/cart", headers=guest(cart_id))).json()["coupon"] is None


async def test_put_coupon_without_cart_422(api: httpx.AsyncClient, redis: Redis) -> None:
    resp = await api.put("/v1/cart/coupon", json={"code": "BEMVINDO10"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "cart.coupon.invalid"
    assert await redis.keys("cart:*") == []


async def test_put_coupon_promotions_down_503(
    api: httpx.AsyncClient, promotions: FakePromotions
) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    promotions.down = True
    resp = await api.put("/v1/cart/coupon", json={"code": "BEMVINDO10"}, headers=guest(cart_id))
    assert resp.status_code == 503
    assert resp.json()["code"] == "cart.promotions.unavailable"


async def test_delete_coupon(api: httpx.AsyncClient) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    await api.put("/v1/cart/coupon", json={"code": "BEMVINDO10"}, headers=guest(cart_id))
    resp = await api.delete("/v1/cart/coupon", headers=guest(cart_id))
    assert resp.status_code == 200
    assert resp.json()["coupon"] is None
    assert resp.json()["discount_cents"] == 0


async def test_promotions_down_get_200_without_discount(
    api: httpx.AsyncClient, promotions: FakePromotions
) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    await api.put("/v1/cart/coupon", json={"code": "BEMVINDO10"}, headers=guest(cart_id))
    promotions.down = True
    await add(api, V2, 1, guest(cart_id))  # nova versão: a avaliação em cache não vale mais
    resp = await api.get("/v1/cart", headers=guest(cart_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["coupon"]["code"] == "BEMVINDO10"
    assert body["coupon"]["valid"] is False
    assert body["coupon"]["reason"] == "promotions.unavailable"
    assert body["discount_cents"] == 0
    assert body["total_cents"] == body["subtotal_cents"] == 10000
    promotions.down = False  # a falha não fica em cache
    assert (await api.get("/v1/cart", headers=guest(cart_id))).json()["discount_cents"] == 1000


async def test_get_reuses_cached_evaluation_for_same_version(
    api: httpx.AsyncClient, promotions: FakePromotions
) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    await api.put("/v1/cart/coupon", json={"code": "BEMVINDO10"}, headers=guest(cart_id))
    promotions.calls.clear()
    for _ in range(3):
        assert (await api.get("/v1/cart", headers=guest(cart_id))).json()["discount_cents"] == 500
    assert len(promotions.calls) <= 1
    await add(api, V1, 1, guest(cart_id))
    calls = len(promotions.calls)
    assert (await api.get("/v1/cart", headers=guest(cart_id))).json()["discount_cents"] == 1000
    assert len(promotions.calls) == calls  # o POST já avaliou e cacheou a versão nova


async def test_coupon_invalid_now_keeps_code_with_reason(
    api: httpx.AsyncClient, promotions: FakePromotions
) -> None:
    cart_id = await new_guest_cart(api, V1, 1)
    await api.put("/v1/cart/coupon", json={"code": "BEMVINDO10"}, headers=guest(cart_id))
    promotions.invalid_now.add("BEMVINDO10")
    resp = await api.patch(f"/v1/cart/items/{V1}", json={"quantity": 2}, headers=guest(cart_id))
    coupon = resp.json()["coupon"]
    assert coupon == {
        "code": "BEMVINDO10",
        "valid": False,
        "reason": "promotions.coupon.expired",
        "min_order_cents": None,
    }
    assert resp.json()["discount_cents"] == 0


async def test_user_coupon_evaluated_with_customer_id(
    api: httpx.AsyncClient,
    promotions: FakePromotions,
    customer: dict[str, str],
    user_id: uuid.UUID,
) -> None:
    await add(api, V1, 1, customer)
    resp = await api.put("/v1/cart/coupon", json={"code": "BEMVINDO10"}, headers=customer)
    assert resp.status_code == 200
    assert promotions.calls[-1] == ("BEMVINDO10", str(user_id))


# ------------------------------------------------------------------ merge


async def test_merge_requires_customer_token(api: httpx.AsyncClient) -> None:
    resp = await api.post("/v1/cart/merge", json={"guest_cart_id": str(uuid.uuid4())})
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.missing_token"


async def test_merge_sums_and_deletes_guest_cart(
    api: httpx.AsyncClient, customer: dict[str, str], redis: Redis, catalog: FakeCatalog
) -> None:
    catalog.variants[V1] = snapshot(V1, available=5)
    await add(api, V1, 3, customer)
    guest_cart = await new_guest_cart(api, V1, 4)
    await add(api, V2, 2, guest(guest_cart))

    resp = await api.post("/v1/cart/merge", json={"guest_cart_id": guest_cart}, headers=customer)
    assert resp.status_code == 200
    body = resp.json()
    assert item(body, V1)["quantity"] == 5
    assert item(body, V1)["notice"] == {
        "code": "quantity_reduced",
        "old_price_cents": None,
        "new_price_cents": None,
        "quantity": 5,
    }
    assert item(body, V2)["quantity"] == 2
    assert body["merge_report"] == {"reduced": [V1], "dropped": []}
    assert await redis.exists(f"cart:{guest_cart}") == 0
    assert await redis.exists(f"cart:{guest_cart}:items") == 0
    assert (await api.get("/v1/cart", headers=guest(guest_cart))).json() == EMPTY
    mine = (await api.get("/v1/cart", headers=customer)).json()
    assert item(mine, V1)["quantity"] == 5
    assert "merge_report" not in mine


async def test_merge_unknown_guest_returns_account_cart(
    api: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    await add(api, V1, 1, customer)
    resp = await api.post(
        "/v1/cart/merge", json={"guest_cart_id": str(uuid.uuid4())}, headers=customer
    )
    assert resp.status_code == 200
    assert item(resp.json(), V1)["quantity"] == 1
    assert resp.json()["merge_report"] == {"reduced": [], "dropped": []}


async def test_merge_user_cart_id_is_ignored(
    api: httpx.AsyncClient, signer: Signer, customer: dict[str, str]
) -> None:
    other = {
        "Authorization": "Bearer "
        + signer.token(sub=uuid.uuid7(), aud="storefront", kind="customer")
    }
    other_cart = (await add(api, V2, 2, other)).json()["cart_id"]
    resp = await api.post("/v1/cart/merge", json={"guest_cart_id": other_cart}, headers=customer)
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert item((await api.get("/v1/cart", headers=other)).json(), V2)["quantity"] == 2


async def test_merge_malformed_id_422(api: httpx.AsyncClient, customer: dict[str, str]) -> None:
    resp = await api.post("/v1/cart/merge", json={"guest_cart_id": "x"}, headers=customer)
    assert resp.status_code == 422
    assert resp.json()["code"] == "cart.cart.invalid_id"


async def test_merge_keeps_valid_guest_coupon(
    api: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    await add(api, V1, 1, customer)
    guest_cart = await new_guest_cart(api, V2, 1)
    await api.put("/v1/cart/coupon", json={"code": "BEMVINDO10"}, headers=guest(guest_cart))
    resp = await api.post("/v1/cart/merge", json={"guest_cart_id": guest_cart}, headers=customer)
    assert resp.json()["coupon"]["code"] == "BEMVINDO10"
    assert resp.json()["discount_cents"] == 1000


async def test_merge_drops_guest_coupon_invalid_for_account(
    api: httpx.AsyncClient,
    customer: dict[str, str],
    promotions: FakePromotions,
    catalog: FakeCatalog,
) -> None:
    catalog.variants[V1] = snapshot(V1, price=60000)
    await add(api, V1, 1, customer)
    await api.put("/v1/cart/coupon", json={"code": "MIN500"}, headers=customer)
    guest_cart = await new_guest_cart(api, V2, 1)
    await api.put("/v1/cart/coupon", json={"code": "BEMVINDO10"}, headers=guest(guest_cart))
    promotions.invalid_now.add("BEMVINDO10")
    resp = await api.post("/v1/cart/merge", json={"guest_cart_id": guest_cart}, headers=customer)
    assert resp.json()["coupon"]["code"] == "MIN500"
    assert resp.json()["coupon"]["valid"] is True
