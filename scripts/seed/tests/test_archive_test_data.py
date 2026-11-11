"""Limpeza local (R26): arquiva pela API de admin os produtos de teste que sobraram na loja."""

import json

import httpx
import pytest

from seed import archive_test_data, data
from seed.client import CatalogAdmin

BASE = "http://api.test"


@pytest.mark.parametrize(
    "slug",
    ["moletom-teste-123", "camiseta-teste-t19", "calca-teste-abc-1", "camiseta-e2e-1794414684000"],
)
def test_test_slugs_match(slug: str) -> None:
    assert archive_test_data.is_test_slug(slug)


@pytest.mark.parametrize("slug", ["moletom-canguru-pesado", "testeira-preta", "camiseta-teste"])
def test_other_slugs_do_not_match(slug: str) -> None:
    assert not archive_test_data.is_test_slug(slug)


def test_no_seed_product_matches() -> None:
    assert not [p.slug for p in data.PRODUCTS if archive_test_data.is_test_slug(p.slug)]


def _api(pages: dict[str | None, dict[str, object]], calls: list[str]) -> CatalogAdmin:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}?{request.url.query.decode()}")
        if request.method == "GET":
            assert request.url.params["status"] == "active"
            return httpx.Response(200, json=pages[request.url.params.get("cursor")])
        return httpx.Response(200, content=json.dumps({"status": "archived"}))

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return CatalogAdmin(http, BASE, "token")


def test_archives_only_matching_active_products_across_pages() -> None:
    pages: dict[str | None, dict[str, object]] = {
        None: {
            "items": [
                {"id": "a", "slug": "moletom-canguru-pesado"},
                {"id": "b", "slug": "moletom-teste-1"},
            ],
            "next_cursor": "c2",
        },
        "c2": {"items": [{"id": "c", "slug": "camiseta-e2e-99"}], "next_cursor": None},
    }
    calls: list[str] = []
    archived = archive_test_data.archive_test_products(_api(pages, calls))
    assert archived == ["moletom-teste-1", "camiseta-e2e-99"]
    posts = [c for c in calls if c.startswith("POST")]
    assert posts == [
        "POST /catalog/v1/admin/products/b/archive?",
        "POST /catalog/v1/admin/products/c/archive?",
    ]


def test_nothing_to_archive_is_a_no_op() -> None:
    calls: list[str] = []
    pages: dict[str | None, dict[str, object]] = {None: {"items": [], "next_cursor": None}}
    assert archive_test_data.archive_test_products(_api(pages, calls)) == []
    assert all(c.startswith("GET") for c in calls)
