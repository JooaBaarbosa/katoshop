import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

type Json = dict[str, Any]


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid7().hex[-10:]}"


@pytest.fixture
def uniq() -> Callable[[str], str]:
    return unique


@pytest.fixture
def admin_client(client: httpx.AsyncClient, admin_token: str) -> httpx.AsyncClient:
    client.headers["Authorization"] = f"Bearer {admin_token}"
    return client


@pytest.fixture
def make_category(admin_client: httpx.AsyncClient) -> Callable[..., Awaitable[Json]]:
    async def make(name: str = "Moletons", **extra: Any) -> Json:
        body = {"name": name, "slug": unique("cat"), **extra}
        response = await admin_client.post("/v1/admin/categories", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    return make


@pytest.fixture
def make_product(
    admin_client: httpx.AsyncClient, make_category: Callable[..., Awaitable[Json]]
) -> Callable[..., Awaitable[Json]]:
    async def make(**overrides: Any) -> Json:
        if "category_id" not in overrides:
            overrides["category_id"] = (await make_category())["id"]
        body: Json = {
            "name": "Moletom Canguru",
            "slug": unique("moletom"),
            "description": "Algodão pesado, felpado por dentro.",
            "base_price_cents": 24900,
            "attributes": {"material": "Algodão", "gramatura": "400 g/m²"},
            **overrides,
        }
        response = await admin_client.post("/v1/admin/products", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    return make


@pytest.fixture
def make_variant(
    admin_client: httpx.AsyncClient, make_product: Callable[..., Awaitable[Json]]
) -> Callable[..., Awaitable[Json]]:
    """Cria um produto com uma variante PRT/M e estoque inicial; devolve a variante."""

    async def make(stock: int = 0) -> Json:
        product = await make_product()
        response = await admin_client.post(
            f"/v1/admin/products/{product['id']}/variants/generate",
            json={"colors": ["PRT"], "sizes": ["M"]},
        )
        assert response.status_code == 200, response.text
        variant = response.json()["variants"][0]
        if stock:
            adjusted = await admin_client.post(
                f"/v1/admin/variants/{variant['id']}/stock-adjustments",
                json={"delta": stock, "reason": "initial"},
            )
            assert adjusted.status_code == 201, adjusted.text
            variant = adjusted.json()["variant"]
        return variant

    return make
