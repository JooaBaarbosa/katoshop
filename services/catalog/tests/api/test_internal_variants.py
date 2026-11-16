import io
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from PIL import Image

type Json = dict[str, Any]
type Factory = Callable[..., Awaitable[Json]]

NOT_FOUND = "catalog.variant.not_found"


def _jpeg(color: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buffer, format="JPEG")
    return buffer.getvalue()


async def _upload(
    admin_client: httpx.AsyncClient, product_id: str, color: str, **fields: str
) -> Json:
    response = await admin_client.post(
        f"/v1/admin/products/{product_id}/images",
        files={"file": ("foto.jpg", _jpeg(color), "image/jpeg")},
        data={"alt": "Foto", **fields},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _get(
    client: httpx.AsyncClient, variant_id: str | uuid.UUID, token: str | None
) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    # O cliente compartilha cabeçalhos com o admin_client: sobrescreve para ficar explícito.
    saved = client.headers.pop("Authorization", None)
    try:
        return await client.get(f"/v1/internal/variants/{variant_id}", headers=headers)
    finally:
        if saved is not None:
            client.headers["Authorization"] = saved


async def test_returns_snapshot_with_exact_fields(
    client: httpx.AsyncClient,
    admin_client: httpx.AsyncClient,
    make_variant: Factory,
    service_token: str,
    uniq: Callable[[str], str],
) -> None:
    variant = await make_variant(stock=7)
    product_id = variant["product_id"]
    product = (await admin_client.get(f"/v1/admin/products/{product_id}")).json()
    patched = await admin_client.patch(
        f"/v1/admin/variants/{variant['id']}",
        json={"version": variant["version"], "price_cents": 19900},
    )
    assert patched.status_code == 200, patched.text
    current = patched.json()
    slugs = []
    for name in ("Zeta", "Alfa"):
        slug = uniq(name.lower())
        slugs.append(slug)
        created = await admin_client.post(
            "/v1/admin/collections", json={"name": name, "slug": slug}
        )
        assert created.status_code == 201, created.text
        linked = await admin_client.put(
            f"/v1/admin/collections/{created.json()['id']}/products",
            json={"product_ids": [product_id]},
        )
        assert linked.status_code == 200, linked.text

    response = await _get(client, variant["id"], service_token)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "variant_id": variant["id"],
        "sku": variant["sku"],
        "product_id": product_id,
        "product_slug": product["slug"],
        "product_status": "draft",
        "name": product["name"],
        "color_code": "PRT",
        "color_name": response.json()["color_name"],
        "size_code": "M",
        "unit_price_cents": 19900,
        "available": 7,
        "active": True,
        "image_url": None,
        "category_slug": product["category"]["slug"],
        "collection_slugs": sorted(slugs),
        "version": current["version"],
    }
    assert response.json()["color_name"]


async def test_unit_price_falls_back_to_product_base_price(
    client: httpx.AsyncClient, make_variant: Factory, service_token: str
) -> None:
    variant = await make_variant(stock=1)

    response = await _get(client, variant["id"], service_token)

    assert response.json()["unit_price_cents"] == 24900


async def test_available_is_zero_when_variant_inactive(
    client: httpx.AsyncClient,
    admin_client: httpx.AsyncClient,
    make_variant: Factory,
    service_token: str,
) -> None:
    variant = await make_variant(stock=5)
    patched = await admin_client.patch(
        f"/v1/admin/variants/{variant['id']}",
        json={"version": variant["version"], "active": False},
    )
    assert patched.status_code == 200, patched.text

    response = await _get(client, variant["id"], service_token)

    assert response.status_code == 200
    assert response.json()["active"] is False
    assert response.json()["available"] == 0


async def test_color_image_wins_over_generic_and_generic_is_fallback(
    client: httpx.AsyncClient,
    admin_client: httpx.AsyncClient,
    make_variant: Factory,
    service_token: str,
) -> None:
    variant = await make_variant(stock=1)
    pid = variant["product_id"]
    generic = await _upload(admin_client, pid, "#111111", position="0")

    only_generic = await _get(client, variant["id"], service_token)
    assert only_generic.json()["image_url"] == generic["url"]

    other_color = await _upload(admin_client, pid, "#222222", color_code="BRC", position="0")
    still_generic = await _get(client, variant["id"], service_token)
    assert still_generic.json()["image_url"] == generic["url"]
    assert other_color["url"] != generic["url"]

    colored = await _upload(admin_client, pid, "#333333", color_code="PRT", position="5")
    response = await _get(client, variant["id"], service_token)
    assert response.json()["image_url"] == colored["url"]


async def test_archived_product_is_still_returned(
    client: httpx.AsyncClient,
    admin_client: httpx.AsyncClient,
    make_variant: Factory,
    service_token: str,
) -> None:
    variant = await make_variant(stock=1)
    archived = await admin_client.post(f"/v1/admin/products/{variant['product_id']}/archive")
    assert archived.status_code == 200, archived.text

    response = await _get(client, variant["id"], service_token)

    assert response.status_code == 200
    assert response.json()["product_status"] == "archived"


async def test_unknown_variant_is_404(client: httpx.AsyncClient, service_token: str) -> None:
    response = await _get(client, uuid.uuid7(), service_token)

    assert response.status_code == 404
    assert response.json()["code"] == NOT_FOUND


async def test_invalid_variant_id_is_422(client: httpx.AsyncClient, service_token: str) -> None:
    response = await _get(client, "nao-e-uuid", service_token)

    assert response.status_code == 422


async def test_storefront_token_is_403(
    client: httpx.AsyncClient, make_variant: Factory, customer_token: str
) -> None:
    variant = await make_variant()

    response = await _get(client, variant["id"], customer_token)

    assert response.status_code == 403
    assert response.json()["code"] == "auth.forbidden"


async def test_missing_token_is_401(client: httpx.AsyncClient, make_variant: Factory) -> None:
    variant = await make_variant()

    response = await _get(client, variant["id"], None)

    assert response.status_code == 401
    assert response.json()["code"] == "auth.missing_token"
