"""Cupons do seed: o upsert pelo código só cria; o que o admin mudou fica como está."""

import json
from collections import Counter
from typing import Any

import httpx

from seed import data
from seed.__main__ import seed_coupons
from seed.client import PromotionsAdmin

BASE = "http://api.test"


def _api(existing: list[dict[str, Any]], calls: list[str], bodies: list[Any]) -> PromotionsAdmin:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        assert request.headers["Authorization"] == "Bearer token"
        if request.method == "GET":
            q = request.url.params["q"]
            items = [c for c in existing if q.upper() in c["code"]]
            return httpx.Response(200, json={"items": items, "next_cursor": None})
        bodies.append(json.loads(request.content))
        return httpx.Response(201, json={"id": "novo", **bodies[-1]})

    return PromotionsAdmin(httpx.Client(transport=httpx.MockTransport(handler)), BASE, "token")


def test_creates_missing_demo_coupon() -> None:
    calls: list[str] = []
    bodies: list[Any] = []
    counts: Counter[str] = Counter()
    seed_coupons(_api([], calls, bodies), counts)
    assert "POST /promotions/v1/admin/coupons" in calls
    assert bodies == [
        {
            "code": "BEMVINDO10",
            "description": "Cupom da loja demonstrativa",
            "kind": "percent",
            "value": 10,
            "min_order_cents": 15000,
            "active": True,
        }
    ]
    assert counts["cupons criados"] == len(data.COUPONS)


def test_existing_coupon_is_never_updated() -> None:
    # o admin mudou valor e desativou: o seed não reverte nada
    changed = {"id": "c1", "code": "BEMVINDO10", "value": 15, "active": False, "version": 3}
    calls: list[str] = []
    bodies: list[Any] = []
    counts: Counter[str] = Counter()
    seed_coupons(_api([changed], calls, bodies), counts)
    assert all(c.startswith("GET") for c in calls)
    assert bodies == []
    assert counts["cupons já existentes"] == 1


def test_lookup_is_exact_by_code() -> None:
    # a busca do admin é por trecho (código ou descrição): BEMVINDO100 não é BEMVINDO10
    other = {"id": "c2", "code": "BEMVINDO100", "value": 5, "active": True, "version": 1}
    calls: list[str] = []
    bodies: list[Any] = []
    seed_coupons(_api([other], calls, bodies), Counter())
    assert [b["code"] for b in bodies] == ["BEMVINDO10"]
