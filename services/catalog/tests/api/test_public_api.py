import base64
import io
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import text

from catalog.application.cursor import encode_cursor
from catalog.settings import CatalogSettings

type Json = dict[str, Any]
type Factory = Callable[..., Awaitable[Json]]

INVALID_CURSOR = "catalog.pagination.invalid_cursor"

SETTINGS: Json = {
    "hero": {
        "title": "Drop de inverno",
        "subtitle": "Moletons e calças de algodão pesado.",
        "cta_label": "Ver o drop atual",
        "cta_href": "/colecoes/drop-inverno",
        "image_key": "products/" + "b" * 64 + ".jpg",
    },
    "secondary_cta": {"label": "Todas as peças", "href": "/c/camisetas"},
    "featured_collection_slugs": ["slug-que-nao-existe"],
    "policies": {
        "shipping_text": "Frete grátis acima de R$ 299 (demo).",
        "returns_text": "Troca em 30 dias (demo).",
        "pix_discount_percent": 5,
        "max_installments": 6,
        "demo_notice": "Loja demonstrativa, nenhuma compra é real",
    },
}


def _jpeg(color: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buffer, format="JPEG")
    return buffer.getvalue()


async def anon_get(client: httpx.AsyncClient, url: str, **params: Any) -> httpx.Response:
    """GET sem o token do admin: as rotas públicas não exigem autenticação."""
    auth = client.headers.pop("Authorization", None)
    try:
        return await client.get(url, params=params)
    finally:
        if auth is not None:
            client.headers["Authorization"] = auth


@pytest.fixture
def publish(admin_client: httpx.AsyncClient, make_product: Factory) -> Factory:
    """Cria um produto com variantes, estoque por variante e uma imagem creditada; publica."""

    async def make(
        *,
        stock: dict[tuple[str, str], int],
        publish: bool = True,
        **product: Any,
    ) -> Json:
        created = await make_product(**product)
        pid = created["id"]
        colors = sorted({c for c, _ in stock})
        sizes = sorted({s for _, s in stock})
        generated = await admin_client.post(
            f"/v1/admin/products/{pid}/variants/generate", json={"colors": colors, "sizes": sizes}
        )
        assert generated.status_code == 200, generated.text
        for variant in generated.json()["variants"]:
            amount = stock.get((variant["color_code"], variant["size_code"]))
            if amount is None:
                patched = await admin_client.patch(
                    f"/v1/admin/variants/{variant['id']}",
                    json={"version": variant["version"], "active": False},
                )
                assert patched.status_code == 200, patched.text
            elif amount:
                adjusted = await admin_client.post(
                    f"/v1/admin/variants/{variant['id']}/stock-adjustments",
                    json={"delta": amount, "reason": "initial"},
                )
                assert adjusted.status_code == 201, adjusted.text
        uploaded = await admin_client.post(
            f"/v1/admin/products/{pid}/images",
            files={"file": ("foto.jpg", _jpeg(f"#{uuid.uuid4().hex[:6]}"), "image/jpeg")},
            data={
                "alt": "Foto de frente",
                "color_code": colors[0],
                "credit_author": "Fulana de Tal",
                "credit_source_url": "https://example.com/foto",
                "license": "CC0",
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        if publish:
            published = await admin_client.post(f"/v1/admin/products/{pid}/publish")
            assert published.status_code == 200, published.text
        fetched = await admin_client.get(f"/v1/admin/products/{pid}")
        return fetched.json()

    return make


async def test_list_products_public_with_cache_header(
    client: httpx.AsyncClient, publish: Factory, make_category: Factory
) -> None:
    category = await make_category()
    product = await publish(category_id=category["id"], stock={("PRT", "M"): 2, ("PRT", "G"): 0})
    response = await anon_get(client, "/v1/products", category=category["slug"])
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "public, max-age=30"
    body = response.json()
    assert body["next_cursor"] is None
    [card] = body["items"]
    assert card["slug"] == product["slug"]
    assert card["min_price_cents"] == 24900
    assert card["sold_out"] is False
    assert card["colors"] == [{"code": "PRT", "name": "Preto", "hex": "#111111"}]
    assert card["image"] == {"url": product["images"][0]["url"], "alt": "Foto de frente"}


async def test_repeatable_size_and_color_params(
    client: httpx.AsyncClient, publish: Factory, make_category: Factory
) -> None:
    category = await make_category()
    medium = await publish(category_id=category["id"], stock={("PRT", "M"): 1})
    large = await publish(category_id=category["id"], stock={("CNZ", "G"): 1})
    await publish(category_id=category["id"], stock={("PRT", "P"): 1})
    params = httpx.QueryParams(
        [
            ("category", category["slug"]),
            ("size", "M"),
            ("size", "G"),
            ("color", "PRT"),
            ("color", "CNZ"),
            ("sort", "price_asc"),
        ]
    )
    auth = client.headers.pop("Authorization", None)
    response = await client.get("/v1/products", params=params)
    unknown = await client.get("/v1/products", params={"category": category["slug"], "size": "ZZZ"})
    if auth is not None:
        client.headers["Authorization"] = auth
    assert response.status_code == 200, response.text
    assert {c["slug"] for c in response.json()["items"]} == {medium["slug"], large["slug"]}
    assert unknown.status_code == 200
    assert unknown.json()["items"] == []


@pytest.mark.parametrize(
    ("q", "status"),
    [
        ("", 200),
        ("   ", 200),
        ("&|!", 200),
        ('"aspas', 200),
        ("x" * 200, 200),
        ("a:* & !b", 200),
        ("'; drop", 200),
        ("\x00", 422),
        ("a\x00b", 422),
        ("linha\nnova", 422),
        ("del\x7f", 422),
    ],
    ids=[
        "empty",
        "spaces",
        "operators",
        "quote",
        "200-chars",
        "prefix-ops",
        "sql",
        "nul",
        "inner-nul",
        "newline",
        "del",
    ],
)
async def test_odd_queries_never_500(client: httpx.AsyncClient, q: str, status: int) -> None:
    # Caracteres de controle são recusados na borda (o Postgres não aceita NUL em texto).
    for sort in ("relevance", "newest"):
        response = await anon_get(client, "/v1/products", q=q, sort=sort)
        assert response.status_code == status, response.text
        facets = await anon_get(client, "/v1/products/facets", q=q)
        assert facets.status_code == status, facets.text
        if status == 422:
            assert response.json()["code"] == "request.validation"


@pytest.mark.parametrize(
    "params",
    [
        {"category": "a\x00"},
        {"collection": "a\x00b"},
        {"category": "Com Espaço"},
        {"category": "x" * 121},
        {"size": "M\x00"},
        {"color": "PRT\x00"},
        {"size": "m"},
        {"color": "PRETO"},
    ],
    ids=[
        "category-nul",
        "collection-nul",
        "category-pattern",
        "category-too-long",
        "size-nul",
        "color-nul",
        "size-lowercase",
        "color-too-long",
    ],
)
async def test_text_params_validated_422(client: httpx.AsyncClient, params: dict[str, str]) -> None:
    for url in ("/v1/products", "/v1/products/facets"):
        response = await anon_get(client, url, **params)
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "request.validation"


async def test_query_too_long_422(client: httpx.AsyncClient) -> None:
    for url in ("/v1/products", "/v1/products/facets"):
        response = await anon_get(client, url, q="x" * 201)
        assert response.status_code == 422
        assert response.json()["code"] == "catalog.search.query_too_long"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.mark.parametrize(
    "cursor",
    [
        "lixo",
        _b64(b'{"s":"newest","k":"2026'),
        _b64(b"[" * 10_000),
        "a" * 513,
        "não-ascii-é",
        encode_cursor({"s": "price_asc", "k": "100", "id": str(uuid.uuid7())}),
        encode_cursor({"s": "newest", "k": "0001-01-01T00:00:00+05:00", "id": str(uuid.uuid7())}),
        encode_cursor({"s": "newest", "k": "9999-12-31T23:59:59-05:00", "id": str(uuid.uuid7())}),
    ],
    ids=[
        "lixo",
        "truncated-json",
        "nested-10k",
        "513-chars",
        "non-ascii",
        "other-sort",
        "year-1-overflow",
        "year-9999-overflow",
    ],
)
async def test_bad_cursor_422(client: httpx.AsyncClient, cursor: str) -> None:
    response = await anon_get(client, "/v1/products", sort="newest", cursor=cursor)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == INVALID_CURSOR


@pytest.mark.parametrize(
    "params",
    [
        {"sort": "popular"},
        {"limit": "0"},
        {"limit": "101"},
        {"price_min": "-1"},
        {"price_max": "abc"},
        {"price_min": "500", "price_max": "100"},
    ],
)
async def test_invalid_params_422(client: httpx.AsyncClient, params: dict[str, str]) -> None:
    response = await anon_get(client, "/v1/products", **params)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "request.validation"


async def test_pagination_over_http(
    client: httpx.AsyncClient, publish: Factory, make_category: Factory
) -> None:
    category = await make_category()
    slugs = {
        (await publish(category_id=category["id"], stock={("PRT", "M"): 1}))["slug"]
        for _ in range(3)
    }
    first = await anon_get(client, "/v1/products", category=category["slug"], limit=2)
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2
    cursor = first.json()["next_cursor"]
    assert cursor
    second = await anon_get(
        client, "/v1/products", category=category["slug"], limit=2, cursor=cursor
    )
    items = first.json()["items"] + second.json()["items"]
    assert {i["slug"] for i in items} == slugs
    assert second.json()["next_cursor"] is None
    reused = await anon_get(
        client, "/v1/products", category=category["slug"], sort="price_asc", cursor=cursor
    )
    assert reused.status_code == 422
    assert reused.json()["code"] == INVALID_CURSOR


async def test_facets_route(
    client: httpx.AsyncClient, publish: Factory, make_category: Factory
) -> None:
    category = await make_category()
    await publish(category_id=category["id"], stock={("PRT", "M"): 1, ("PRT", "P"): 1})
    await publish(category_id=category["id"], stock={("CNZ", "G"): 1})
    response = await anon_get(client, "/v1/products/facets", category=category["slug"], size="M")
    assert response.status_code == 200, response.text
    body = response.json()
    sizes = {s["code"]: s["count"] for s in body["sizes"]}
    assert (sizes["P"], sizes["M"], sizes["G"]) == (1, 1, 1)
    assert body["sizes"][0] == {"code": "PP", "label": "PP", "count": 0}
    colors = {c["code"]: c for c in body["colors"]}
    assert colors["PRT"] == {"code": "PRT", "name": "Preto", "hex": "#111111", "count": 1}
    assert colors["CNZ"]["count"] == 0
    assert {"slug": category["slug"], "name": category["name"], "count": 1} in body["categories"]
    assert body["price"] == {"min": 24900, "max": 24900}


async def test_detail(
    client: httpx.AsyncClient,
    admin_client: httpx.AsyncClient,
    publish: Factory,
    settings: CatalogSettings,
) -> None:
    product = await publish(
        stock={("PRT", "M"): 3, ("PRT", "G"): 0, ("CNZ", "M"): 1},
        attributes={"material": "Algodão"},
    )
    cnz_m = next(
        v for v in product["variants"] if (v["color_code"], v["size_code"]) == ("CNZ", "M")
    )
    repriced = await admin_client.patch(
        f"/v1/admin/variants/{cnz_m['id']}",
        json={"version": cnz_m["version"], "price_cents": 19900},
    )
    assert repriced.status_code == 200, repriced.text
    response = await anon_get(client, f"/v1/products/{product['slug']}")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "public, max-age=30"
    body = response.json()
    assert body["slug"] == product["slug"]
    assert body["name"] == product["name"]
    assert body["description"] == product["description"]
    assert body["attributes"] == {"material": "Algodão"}
    assert body["category"] == {"slug": product["category"]["slug"], "name": "Moletons"}
    assert body["min_price_cents"] == 19900
    assert body["colors"] == [
        {"code": "CNZ", "name": "Cinza mescla", "hex": "#8C8C88"},
        {"code": "PRT", "name": "Preto", "hex": "#111111"},
    ]
    assert body["sizes"] == [{"code": "M", "label": "M"}, {"code": "G", "label": "G"}]
    variants = {(v["color_code"], v["size_code"]): v for v in body["variants"]}
    # A combinação CNZ/G foi gerada e desativada: não aparece.
    assert set(variants) == {("PRT", "M"), ("PRT", "G"), ("CNZ", "M")}
    assert variants[("PRT", "M")]["available"] is True
    assert variants[("PRT", "G")]["available"] is False
    assert variants[("CNZ", "M")]["price_cents"] == 19900
    assert variants[("PRT", "M")]["price_cents"] == 24900
    assert set(variants[("PRT", "M")]) == {
        "sku",
        "color_code",
        "size_code",
        "price_cents",
        "available",
    }
    [image] = body["images"]
    key = product["images"][0]["storage_key"]
    assert image == {
        "url": f"{settings.public_base_url}/v1/media/{key}",
        "alt": "Foto de frente",
        "color_code": "CNZ",
        "width": 40,
        "height": 30,
        "credit_author": "Fulana de Tal",
        "credit_source_url": "https://example.com/foto",
        "license": "CC0",
    }


async def test_detail_inactive_404(
    client: httpx.AsyncClient, admin_client: httpx.AsyncClient, publish: Factory
) -> None:
    draft = await publish(stock={("PRT", "M"): 1}, publish=False)
    archived = await publish(stock={("PRT", "M"): 1})
    done = await admin_client.post(f"/v1/admin/products/{archived['id']}/archive")
    assert done.status_code == 200, done.text
    # Slug fora do padrão (NUL, maiúsculas, longo demais) é só um produto inexistente.
    for slug in (draft["slug"], archived["slug"], "nao-existe", "x" * 300, "a%00b", "Maiusc"):
        response = await anon_get(client, f"/v1/products/{slug}")
        assert response.status_code == 404, slug
        assert response.json()["code"] == "catalog.product.not_found"
    listed = await anon_get(client, "/v1/products", category=archived["category"]["slug"])
    assert listed.json()["items"] == []


async def test_categories(client: httpx.AsyncClient, make_category: Factory) -> None:
    category = await make_category("Calças")
    response = await anon_get(client, "/v1/categories")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=30"
    found = [c for c in response.json()["items"] if c["slug"] == category["slug"]]
    assert found == [
        {"slug": category["slug"], "name": "Calças", "parent_slug": None, "position": 0}
    ]


async def test_collections(
    client: httpx.AsyncClient,
    admin_client: httpx.AsyncClient,
    publish: Factory,
    uniq: Callable[[str], str],
) -> None:
    inside = await publish(stock={("PRT", "M"): 1})
    await publish(stock={("PRT", "M"): 1}, category_id=inside["category"]["id"])
    slug = uniq("drop")
    created = await admin_client.post(
        "/v1/admin/collections",
        json={
            "name": "Drop de inverno",
            "slug": slug,
            "description": "Peças novas",
            "featured": True,
        },
    )
    assert created.status_code == 201, created.text
    linked = await admin_client.put(
        f"/v1/admin/collections/{created.json()['id']}/products",
        json={"product_ids": [inside["id"]]},
    )
    assert linked.status_code == 200, linked.text
    expected = {
        "slug": slug,
        "name": "Drop de inverno",
        "description": "Peças novas",
        "featured": True,
        "position": 0,
    }
    listed = await anon_get(client, "/v1/collections")
    assert listed.status_code == 200
    assert expected in listed.json()["items"]
    detail = await anon_get(client, f"/v1/collections/{slug}")
    assert detail.status_code == 200
    assert detail.json() == expected
    for absent in ("nao-existe", "a%00b", "x" * 200):
        missing = await anon_get(client, f"/v1/collections/{absent}")
        assert missing.status_code == 404
        assert missing.json()["code"] == "catalog.collection.not_found"
    products = await anon_get(client, "/v1/products", collection=slug)
    assert [p["slug"] for p in products.json()["items"]] == [inside["slug"]]


async def test_storefront_settings(
    app: FastAPI, client: httpx.AsyncClient, admin_client: httpx.AsyncClient
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(text("DELETE FROM storefront_settings"))
    missing = await anon_get(client, "/v1/storefront/settings")
    assert missing.status_code == 404
    assert missing.json()["code"] == "catalog.storefront.settings_not_found"
    saved = await admin_client.put("/v1/admin/storefront/settings", json=SETTINGS)
    assert saved.status_code == 200, saved.text
    response = await anon_get(client, "/v1/storefront/settings")
    assert response.status_code == 200
    assert response.json() == SETTINGS


async def test_credits(
    client: httpx.AsyncClient, publish: Factory, uniq: Callable[[str], str]
) -> None:
    name = uniq("Moletom creditado")
    product = await publish(stock={("PRT", "M"): 1}, name=name)
    hidden = uniq("Rascunho creditado")
    await publish(stock={("PRT", "M"): 1}, name=hidden, publish=False)
    response = await anon_get(client, "/v1/credits")
    assert response.status_code == 200
    items = response.json()["items"]
    assert {
        "product_name": name,
        "image_url": product["images"][0]["url"],
        "credit_author": "Fulana de Tal",
        "credit_source_url": "https://example.com/foto",
        "license": "CC0",
    } in items
    assert all(i["product_name"] != hidden for i in items)


@pytest.mark.parametrize(
    ("sql", "params"),
    [
        ("SELECT CAST(:v AS text)", {"v": "a\x00b"}),
        ("SELECT make_timestamp(2026, 13, 1, 0, 0, 0)", {}),
    ],
    ids=["22021-nul-byte", "22008-datetime-overflow"],
)
async def test_db_input_errors_map_to_422(
    app: FastAPI, client: httpx.AsyncClient, sql: str, params: dict[str, str]
) -> None:
    """Defesa em profundidade: entrada que escapou da validação vira 422, não 500."""

    async def broken() -> dict[str, str]:
        async with app.state.session_factory() as session:
            await session.execute(text(sql), params)
        return {}

    app.add_api_route("/test/db-input-error", broken)
    response = await client.get("/test/db-input-error")
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "request.validation"


async def test_other_db_errors_stay_500(app: FastAPI, client: httpx.AsyncClient) -> None:
    async def broken() -> dict[str, str]:
        async with app.state.session_factory() as session:
            await session.execute(text("SELECT 1 / 0"))
        return {}

    app.add_api_route("/test/db-other-error", broken)
    response = await client.get("/test/db-other-error")
    assert response.status_code == 500
    assert response.json()["code"] == "internal.error"
