from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import text

type Json = dict[str, Any]
type Factory = Callable[..., Awaitable[Json]]

VALID_SETTINGS: Json = {
    "hero": {
        "title": "Drop de inverno",
        "subtitle": "Moletons e calças de algodão pesado.",
        "cta_label": "Ver o drop atual",
        "cta_href": "/colecoes/drop-inverno",
        "image_key": "products/" + "a" * 64 + ".jpg",
    },
    "secondary_cta": {"label": "Todas as peças", "href": "/c/camisetas"},
    "featured_collection_slugs": ["drop-inverno"],
    "policies": {
        "shipping_text": "Frete grátis acima de R$ 299 (demo).",
        "returns_text": "Troca em 30 dias (demo).",
        "pix_discount_percent": 5,
        "max_installments": 6,
        "demo_notice": "Loja demonstrativa, nenhuma compra é real",
    },
}


async def test_category_crud(admin_client: httpx.AsyncClient, uniq: Callable[[str], str]) -> None:
    created = await admin_client.post("/v1/admin/categories", json={"name": "Calças Jeans"})
    assert created.status_code == 201, created.text
    category = created.json()
    assert category["slug"] == "calcas-jeans"

    listed = await admin_client.get("/v1/admin/categories")
    assert listed.status_code == 200
    assert category["id"] in [c["id"] for c in listed.json()["items"]]

    new_slug = uniq("calcas")
    patched = await admin_client.patch(
        f"/v1/admin/categories/{category['id']}", json={"name": "Calças", "slug": new_slug}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Calças"
    assert patched.json()["slug"] == new_slug

    deleted = await admin_client.delete(f"/v1/admin/categories/{category['id']}")
    assert deleted.status_code == 204
    missing = await admin_client.delete(f"/v1/admin/categories/{category['id']}")
    assert missing.status_code == 404
    assert missing.json()["code"] == "catalog.category.not_found"


async def test_category_duplicate_slug_409(
    admin_client: httpx.AsyncClient, make_category: Factory
) -> None:
    category = await make_category()
    response = await admin_client.post(
        "/v1/admin/categories", json={"name": "Outra", "slug": category["slug"]}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "catalog.category.slug_taken"


async def test_category_in_use_409(admin_client: httpx.AsyncClient, make_product: Factory) -> None:
    product = await make_product()
    response = await admin_client.delete(f"/v1/admin/categories/{product['category_id']}")
    assert response.status_code == 409
    assert response.json()["code"] == "catalog.category.in_use"


async def test_category_rename_updates_product_name_cache(
    app: FastAPI, admin_client: httpx.AsyncClient, make_product: Factory
) -> None:
    product = await make_product()
    await admin_client.patch(
        f"/v1/admin/categories/{product['category_id']}", json={"name": "Agasalhos"}
    )
    fetched = await admin_client.get(f"/v1/admin/products/{product['id']}")
    assert fetched.json()["category"]["name"] == "Agasalhos"
    async with app.state.session_factory() as session:
        cache = await session.scalar(
            text("SELECT category_name_cache FROM products WHERE id = :id"), {"id": product["id"]}
        )
    assert cache == "Agasalhos"


async def _set_parent(client: httpx.AsyncClient, category: Json, parent: Json) -> httpx.Response:
    return await client.patch(
        f"/v1/admin/categories/{category['id']}", json={"parent_id": parent["id"]}
    )


async def test_category_parent_cycle_422(
    admin_client: httpx.AsyncClient, make_category: Factory
) -> None:
    a, b, c = await make_category("A"), await make_category("B"), await make_category("C")

    itself = await _set_parent(admin_client, a, a)
    assert itself.status_code == 422
    assert itself.json()["code"] == "catalog.category.parent_cycle"

    assert (await _set_parent(admin_client, b, a)).status_code == 200  # B sob A
    two_levels = await _set_parent(admin_client, a, b)  # A sob B fecharia A -> B -> A
    assert two_levels.status_code == 422
    assert two_levels.json()["code"] == "catalog.category.parent_cycle"

    assert (await _set_parent(admin_client, c, b)).status_code == 200  # C sob B sob A
    three_levels = await _set_parent(admin_client, a, c)  # A -> C -> B -> A
    assert three_levels.status_code == 422
    assert three_levels.json()["code"] == "catalog.category.parent_cycle"

    listed = {x["id"]: x for x in (await admin_client.get("/v1/admin/categories")).json()["items"]}
    assert listed[a["id"]]["parent_id"] is None
    assert listed[b["id"]]["parent_id"] == a["id"]
    assert listed[c["id"]]["parent_id"] == b["id"]


async def test_collection_crud_and_product_order(
    admin_client: httpx.AsyncClient, make_product: Factory, uniq: Callable[[str], str]
) -> None:
    first, second = await make_product(), await make_product()
    created = await admin_client.post(
        "/v1/admin/collections",
        json={"name": "Drop de inverno", "slug": uniq("drop"), "featured": True},
    )
    assert created.status_code == 201, created.text
    collection = created.json()
    assert collection["product_ids"] == []

    ordered = await admin_client.put(
        f"/v1/admin/collections/{collection['id']}/products",
        json={"product_ids": [second["id"], first["id"]]},
    )
    assert ordered.status_code == 200, ordered.text
    assert ordered.json()["product_ids"] == [second["id"], first["id"]]

    reordered = await admin_client.put(
        f"/v1/admin/collections/{collection['id']}/products",
        json={"product_ids": [first["id"]]},
    )
    assert reordered.json()["product_ids"] == [first["id"]]

    patched = await admin_client.patch(
        f"/v1/admin/collections/{collection['id']}", json={"description": "Peças quentes"}
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "Peças quentes"
    listed = await admin_client.get("/v1/admin/collections")
    assert collection["id"] in [c["id"] for c in listed.json()["items"]]

    deleted = await admin_client.delete(f"/v1/admin/collections/{collection['id']}")
    assert deleted.status_code == 204


async def test_collection_products_unknown_product_404(
    admin_client: httpx.AsyncClient, uniq: Callable[[str], str]
) -> None:
    collection = (
        await admin_client.post("/v1/admin/collections", json={"name": "X", "slug": uniq("x")})
    ).json()
    response = await admin_client.put(
        f"/v1/admin/collections/{collection['id']}/products",
        json={"product_ids": ["0190f0f0-0000-7000-8000-000000000000"]},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "catalog.product.not_found"


async def test_customer_token_403(client: httpx.AsyncClient, customer_token: str) -> None:
    response = await client.get(
        "/v1/admin/products", headers={"Authorization": f"Bearer {customer_token}"}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "auth.forbidden"


async def test_staff_without_permission_403(
    client: httpx.AsyncClient, staff_without_roles_token: str
) -> None:
    response = await client.post(
        "/v1/admin/categories",
        json={"name": "Nada"},
        headers={"Authorization": f"Bearer {staff_without_roles_token}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "auth.insufficient_permission"


async def test_no_token_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/admin/overview")
    assert response.status_code == 401
    assert response.json()["code"] == "auth.missing_token"


async def test_storefront_settings_put_validates(admin_client: httpx.AsyncClient) -> None:
    external = {**VALID_SETTINGS, "secondary_cta": {"label": "Fora", "href": "//evil.example"}}
    rejected = await admin_client.put("/v1/admin/storefront/settings", json=external)
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "request.validation"

    saved = await admin_client.put("/v1/admin/storefront/settings", json=VALID_SETTINGS)
    assert saved.status_code == 200, saved.text
    assert saved.json() == VALID_SETTINGS

    fetched = await admin_client.get("/v1/admin/storefront/settings")
    assert fetched.status_code == 200
    assert fetched.json() == VALID_SETTINGS
