import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import text

from catalog.adapters.models import ProductImage

type Json = dict[str, Any]
type Factory = Callable[..., Awaitable[Json]]


async def _generate(
    client: httpx.AsyncClient, product_id: str, colors: list[str], sizes: list[str]
):
    return await client.post(
        f"/v1/admin/products/{product_id}/variants/generate",
        json={"colors": colors, "sizes": sizes},
    )


async def _add_image(app: FastAPI, product_id: str) -> None:
    async with app.state.session_factory() as session, session.begin():
        session.add(
            ProductImage(
                product_id=uuid.UUID(product_id),
                storage_key="products/" + "b" * 64 + ".jpg",
                width=1200,
                height=1500,
                alt="Moletom preto dobrado",
            )
        )


async def test_create_product_generates_slug_and_draft_status(
    admin_client: httpx.AsyncClient, make_category: Factory, uniq: Callable[[str], str]
) -> None:
    category = await make_category("Camisetas")
    name = f"Camiseta Básica Ção {uniq('x')}"
    response = await admin_client.post(
        "/v1/admin/products",
        json={
            "name": name,
            "description": "Malha 30.1",
            "category_id": category["id"],
            "base_price_cents": 8900,
            "attributes": {"modelagem": "reta"},
        },
    )
    assert response.status_code == 201, response.text
    product = response.json()
    assert product["slug"].startswith("camiseta-basica-cao-x-")
    assert product["status"] == "draft"
    assert product["version"] == 1
    assert product["variants"] == []
    assert product["images"] == []
    assert product["category"] == {
        "id": category["id"],
        "slug": category["slug"],
        "name": "Camisetas",
    }
    assert product["published_at"] is None
    assert product["min_price_cents"] is None


async def test_duplicate_slug_409(admin_client: httpx.AsyncClient, make_product: Factory) -> None:
    product = await make_product()
    response = await admin_client.post(
        "/v1/admin/products",
        json={
            "name": "Outro",
            "slug": product["slug"],
            "description": "",
            "category_id": product["category_id"],
            "base_price_cents": 100,
            "attributes": {},
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "catalog.product.slug_taken"


async def test_create_product_unknown_category_404(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.post(
        "/v1/admin/products",
        json={
            "name": "Sem categoria",
            "description": "",
            "category_id": str(uuid.uuid7()),
            "base_price_cents": 100,
            "attributes": {},
        },
    )
    assert response.status_code == 404
    assert response.json()["code"] == "catalog.category.not_found"


async def test_patch_with_stale_version_409(
    admin_client: httpx.AsyncClient, make_product: Factory
) -> None:
    product = await make_product()
    ok = await admin_client.patch(
        f"/v1/admin/products/{product['id']}", json={"name": "Moletom Novo", "version": 1}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["name"] == "Moletom Novo"
    assert ok.json()["version"] == 2

    stale = await admin_client.patch(
        f"/v1/admin/products/{product['id']}", json={"name": "Perdida", "version": 1}
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "catalog.product.version_conflict"
    current = await admin_client.get(f"/v1/admin/products/{product['id']}")
    assert current.json()["name"] == "Moletom Novo"


async def test_patch_requires_version(
    admin_client: httpx.AsyncClient, make_product: Factory
) -> None:
    product = await make_product()
    response = await admin_client.patch(
        f"/v1/admin/products/{product['id']}", json={"name": "Sem versão"}
    )
    assert response.status_code == 422


async def test_patch_category_updates_name_cache(
    app: FastAPI, admin_client: httpx.AsyncClient, make_product: Factory, make_category: Factory
) -> None:
    product = await make_product()
    other = await make_category("Acessórios")
    response = await admin_client.patch(
        f"/v1/admin/products/{product['id']}",
        json={"category_id": other["id"], "version": product["version"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["category"]["name"] == "Acessórios"
    async with app.state.session_factory() as session:
        cache = await session.scalar(
            text("SELECT category_name_cache FROM products WHERE id = :id"), {"id": product["id"]}
        )
    assert cache == "Acessórios"


async def test_unknown_product_404(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get(f"/v1/admin/products/{uuid.uuid7()}")
    assert response.status_code == 404
    assert response.json()["code"] == "catalog.product.not_found"


async def test_generate_variants_idempotent(
    admin_client: httpx.AsyncClient, make_product: Factory
) -> None:
    product = await make_product()
    first = await _generate(admin_client, product["id"], ["PRT", "CNZ"], ["P", "M", "G"])
    assert first.status_code == 200, first.text
    assert len(first.json()["variants"]) == 6
    second = await _generate(admin_client, product["id"], ["PRT", "CNZ"], ["P", "M", "G"])
    assert second.status_code == 200
    assert len(second.json()["variants"]) == 6
    assert {v["id"] for v in first.json()["variants"]} == {
        v["id"] for v in second.json()["variants"]
    }
    more = await _generate(admin_client, product["id"], ["PRT"], ["GG"])
    assert len(more.json()["variants"]) == 7
    variant = more.json()["variants"][0]
    assert variant["sku"].startswith("KS-")
    assert variant["stock_on_hand"] == 0
    assert variant["available"] == 0
    assert variant["price_cents"] is None
    assert variant["effective_price_cents"] == product["base_price_cents"]
    assert more.json()["min_price_cents"] == product["base_price_cents"]


async def test_generate_unknown_option_422(
    admin_client: httpx.AsyncClient, make_product: Factory
) -> None:
    product = await make_product()
    response = await _generate(admin_client, product["id"], ["PRT", "ROX"], ["M", "XXXG"])
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "catalog.variant.unknown_option"
    assert body["errors"] == {"colors": ["ROX"], "sizes": ["XXXG"]}


async def test_min_price_recomputed_on_variant_price_change(
    admin_client: httpx.AsyncClient, make_product: Factory
) -> None:
    product = await make_product(base_price_cents=24900)
    generated = (await _generate(admin_client, product["id"], ["PRT"], ["P", "M"])).json()
    assert generated["min_price_cents"] == 24900
    variant = generated["variants"][0]

    patched = await admin_client.patch(
        f"/v1/admin/variants/{variant['id']}",
        json={"price_cents": 19900, "version": variant["version"]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["price_cents"] == 19900
    assert patched.json()["version"] == variant["version"] + 1
    current = (await admin_client.get(f"/v1/admin/products/{product['id']}")).json()
    assert current["min_price_cents"] == 19900

    deactivated = await admin_client.patch(
        f"/v1/admin/variants/{variant['id']}",
        json={"active": False, "version": patched.json()["version"]},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["price_cents"] == 19900
    current = (await admin_client.get(f"/v1/admin/products/{product['id']}")).json()
    assert current["min_price_cents"] == 24900

    base_change = await admin_client.patch(
        f"/v1/admin/products/{product['id']}",
        json={"base_price_cents": 15900, "version": current["version"]},
    )
    assert base_change.json()["min_price_cents"] == 15900


async def test_variant_patch_stale_version_409(
    admin_client: httpx.AsyncClient, make_variant: Factory
) -> None:
    variant = await make_variant()
    response = await admin_client.patch(
        f"/v1/admin/variants/{variant['id']}",
        json={"price_cents": None, "version": variant["version"] + 5},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "catalog.variant.version_conflict"


async def test_publish_blocked_lists_reasons(
    admin_client: httpx.AsyncClient, make_product: Factory
) -> None:
    product = await make_product()
    response = await admin_client.post(f"/v1/admin/products/{product['id']}/publish")
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "catalog.product.not_publishable"
    assert body["errors"] == {"product": ["no_active_variant", "no_image"]}


async def test_publish_ok_sets_published_at(
    app: FastAPI, admin_client: httpx.AsyncClient, make_product: Factory
) -> None:
    product = await make_product()
    await _generate(admin_client, product["id"], ["PRT"], ["M"])
    await _add_image(app, product["id"])

    response = await admin_client.post(f"/v1/admin/products/{product['id']}/publish")
    assert response.status_code == 200, response.text
    published = response.json()
    assert published["status"] == "active"
    assert published["published_at"] is not None
    assert published["version"] == product["version"] + 1
    assert len(published["images"]) == 1
    assert published["images"][0]["alt"] == "Moletom preto dobrado"

    archived = await admin_client.post(f"/v1/admin/products/{product['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["published_at"] == published["published_at"]


async def test_list_products_filters_and_cursor(
    admin_client: httpx.AsyncClient,
    make_product: Factory,
    make_category: Factory,
    uniq: Callable[[str], str],
) -> None:
    category = await make_category("Calças")
    tag = uniq("jogger")
    created: list[Json] = []
    for i in range(3):
        created.append(await make_product(name=f"Calça {tag} {i}", category_id=category["id"]))
        if i == 0:
            await _generate(admin_client, created[0]["id"], ["PRT", "BRC"], ["M"])

    page1 = await admin_client.get(
        "/v1/admin/products", params={"category": category["slug"], "limit": 2}
    )
    assert page1.status_code == 200, page1.text
    body1 = page1.json()
    assert len(body1["items"]) == 2
    assert body1["next_cursor"]
    page2 = await admin_client.get(
        "/v1/admin/products",
        params={"category": category["slug"], "limit": 2, "cursor": body1["next_cursor"]},
    )
    body2 = page2.json()
    assert len(body2["items"]) == 1
    assert body2["next_cursor"] is None
    ids = [row["id"] for row in body1["items"] + body2["items"]]
    assert ids == [p["id"] for p in reversed(created)]

    row = next(r for r in body2["items"] + body1["items"] if r["id"] == created[0]["id"])
    assert row["variant_count"] == 2
    assert row["total_available"] == 0
    assert row["category"]["slug"] == category["slug"]
    assert row["status"] == "draft"
    assert row["min_price_cents"] == created[0]["base_price_cents"]

    searched = await admin_client.get("/v1/admin/products", params={"q": f"{tag} 1"})
    assert [r["id"] for r in searched.json()["items"]] == [created[1]["id"]]
    by_slug = await admin_client.get("/v1/admin/products", params={"slug": created[2]["slug"]})
    assert [r["id"] for r in by_slug.json()["items"]] == [created[2]["id"]]
    by_status = await admin_client.get(
        "/v1/admin/products", params={"category": category["slug"], "status": "active"}
    )
    assert by_status.json()["items"] == []


async def test_list_products_invalid_cursor_422(admin_client: httpx.AsyncClient) -> None:
    for cursor in ["nao-e-base64!!", "eyJ4IjogMX0", "e30"]:
        response = await admin_client.get("/v1/admin/products", params={"cursor": cursor})
        assert response.status_code == 422, cursor
        assert response.json()["code"] == "catalog.pagination.invalid_cursor"


async def test_list_products_odd_query_no_500(admin_client: httpx.AsyncClient) -> None:
    for q in ["", "   ", "%_\\", '"&|!']:
        response = await admin_client.get("/v1/admin/products", params={"q": q})
        assert response.status_code == 200, q
