import asyncio
import base64
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import text

type Json = dict[str, Any]
type Factory = Callable[..., Awaitable[Json]]


def _b64_json(value: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()


async def _movement_count(app: FastAPI, variant_id: str) -> int:
    async with app.state.session_factory() as session:
        count = await session.scalar(
            text("SELECT count(*) FROM stock_movements WHERE variant_id = :id"), {"id": variant_id}
        )
    return int(count or 0)


async def test_stock_adjustment_records_movement_with_actor(
    app: FastAPI,
    admin_client: httpx.AsyncClient,
    admin_user_id: uuid.UUID,
    make_variant: Factory,
) -> None:
    variant = await make_variant()
    response = await admin_client.post(
        f"/v1/admin/variants/{variant['id']}/stock-adjustments",
        json={"delta": 7, "reason": "initial", "note": "Contagem inicial"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["variant"]["stock_on_hand"] == 7
    assert body["variant"]["available"] == 7
    movement = body["movement"]
    assert movement["delta"] == 7
    assert movement["reason"] == "initial"
    assert movement["note"] == "Contagem inicial"
    assert movement["actor_id"] == str(admin_user_id)
    assert movement["variant_id"] == variant["id"]

    async with app.state.session_factory() as session:
        row = (
            await session.execute(
                text("SELECT delta, actor_id FROM stock_movements WHERE id = :id"),
                {"id": movement["id"]},
            )
        ).one()
    assert (row.delta, row.actor_id) == (7, admin_user_id)


async def test_stock_adjustment_negative_422(
    app: FastAPI, admin_client: httpx.AsyncClient, make_variant: Factory
) -> None:
    variant = await make_variant(stock=2)
    before = await _movement_count(app, variant["id"])
    response = await admin_client.post(
        f"/v1/admin/variants/{variant['id']}/stock-adjustments",
        json={"delta": -3, "reason": "damage"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "catalog.stock.would_go_negative"
    assert await _movement_count(app, variant["id"]) == before


async def test_stock_adjustment_rejects_system_reason_and_zero(
    admin_client: httpx.AsyncClient, make_variant: Factory
) -> None:
    variant = await make_variant(stock=2)
    url = f"/v1/admin/variants/{variant['id']}/stock-adjustments"
    sale = await admin_client.post(url, json={"delta": -1, "reason": "sale"})
    assert sale.status_code == 422
    assert sale.json()["code"] == "catalog.stock.invalid_reason"
    zero = await admin_client.post(url, json={"delta": 0, "reason": "adjustment"})
    assert zero.status_code == 422
    assert zero.json()["code"] == "catalog.stock.zero_delta"


async def test_stock_adjustment_unknown_variant_404(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.post(
        f"/v1/admin/variants/{uuid.uuid7()}/stock-adjustments",
        json={"delta": 1, "reason": "adjustment"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "catalog.variant.not_found"


async def test_concurrent_stock_adjustments_serialize(
    app: FastAPI, admin_client: httpx.AsyncClient, make_variant: Factory
) -> None:
    variant = await make_variant(stock=5)
    before = await _movement_count(app, variant["id"])
    url = f"/v1/admin/variants/{variant['id']}/stock-adjustments"

    responses = await asyncio.gather(
        admin_client.post(url, json={"delta": -3, "reason": "adjustment"}),
        admin_client.post(url, json={"delta": -3, "reason": "adjustment"}),
    )

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201, 422], [r.text for r in responses]
    rejected = next(r for r in responses if r.status_code == 422)
    assert rejected.json()["code"] == "catalog.stock.would_go_negative"
    async with app.state.session_factory() as session:
        on_hand = await session.scalar(
            text("SELECT stock_on_hand FROM variants WHERE id = :id"), {"id": variant["id"]}
        )
    assert on_hand == 2
    assert await _movement_count(app, variant["id"]) == before + 1


async def test_stock_movements_newest_first_with_cursor(
    admin_client: httpx.AsyncClient, make_variant: Factory
) -> None:
    variant = await make_variant(stock=10)
    url = f"/v1/admin/variants/{variant['id']}/stock-adjustments"
    for delta in (-1, -2, 4):
        response = await admin_client.post(url, json={"delta": delta, "reason": "adjustment"})
        assert response.status_code == 201

    movements_url = f"/v1/admin/variants/{variant['id']}/stock-movements"
    page1 = (await admin_client.get(movements_url, params={"limit": 3})).json()
    assert [m["delta"] for m in page1["items"]] == [4, -2, -1]
    page2 = (
        await admin_client.get(movements_url, params={"limit": 3, "cursor": page1["next_cursor"]})
    ).json()
    assert [m["delta"] for m in page2["items"]] == [10]
    assert page2["next_cursor"] is None

    product_style = _b64_json({"u": "2026-10-24T00:00:00+00:00", "i": str(uuid.uuid7())})
    bad_cursors = [
        "lixo",
        product_style,
        _b64_json({"c": "2026-10-24T00:00:00+00:00", "i": 5}),
        _b64_json({"c": 1729728000, "i": str(uuid.uuid7())}),
        _b64_json(["2026-10-24T00:00:00+00:00", str(uuid.uuid7())]),
        _b64_json(None),
    ]
    for cursor in bad_cursors:
        bad = await admin_client.get(movements_url, params={"cursor": cursor})
        assert bad.status_code == 422, cursor
        assert bad.json()["code"] == "catalog.pagination.invalid_cursor"


async def test_overview(admin_client: httpx.AsyncClient, make_variant: Factory) -> None:
    empty_variant = await make_variant()
    stocked = await make_variant(stock=3)

    response = await admin_client.get("/v1/admin/overview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body["products_by_status"]) == {"draft", "active", "archived"}
    assert body["products_by_status"]["draft"] >= 2
    assert body["out_of_stock_variants"] >= 1
    recent = body["recent_movements"]
    assert 1 <= len(recent) <= 10
    assert recent[0]["variant_id"] == stocked["id"]
    assert recent[0]["sku"] == stocked["sku"]
    assert recent[0]["product_name"]
    assert empty_variant["id"] not in [m["variant_id"] for m in recent]
