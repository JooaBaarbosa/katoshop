import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

type Json = dict[str, Any]

BASE = "/v1/admin/coupons"


async def create(client: httpx.AsyncClient, code: str, **overrides: Any) -> Json:
    response = await client.post(
        BASE, json={"code": code, "kind": "percent", "value": 10, **overrides}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_crud_roundtrip(
    admin_client: httpx.AsyncClient, new_code: Callable[[str], str]
) -> None:
    code = new_code("BEMVINDO")
    created = await create(
        admin_client,
        f" {code.lower()} ",
        description="Primeira compra",
        min_order_cents=5000,
        starts_at="2026-12-01T00:00:00Z",
        ends_at="2026-12-31T00:00:00Z",
        category_slugs=["moletons", "moletons"],
        max_uses_total=100,
    )
    assert created["code"] == code
    assert created["version"] == 1
    assert created["active"] is True
    assert created["uses_count"] == 0
    assert created["category_slugs"] == ["moletons"]
    assert created["collection_slugs"] == []

    fetched = await admin_client.get(f"{BASE}/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created

    patched = await admin_client.patch(
        f"{BASE}/{created['id']}", json={"version": 1, "value": 15, "description": "Nova"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["value"] == 15
    assert patched.json()["description"] == "Nova"
    assert patched.json()["version"] == 2
    assert patched.json()["min_order_cents"] == 5000

    cleared = await admin_client.patch(
        f"{BASE}/{created['id']}", json={"version": 2, "min_order_cents": None}
    )
    assert cleared.json()["min_order_cents"] is None

    deleted = await admin_client.delete(f"{BASE}/{created['id']}")
    assert deleted.status_code == 204
    assert (await admin_client.get(f"{BASE}/{created['id']}")).status_code == 404


async def test_duplicate_code_409(
    admin_client: httpx.AsyncClient, new_code: Callable[[str], str]
) -> None:
    first = await create(admin_client, new_code("DUP"))
    response = await admin_client.post(
        BASE, json={"code": first["code"].lower(), "kind": "fixed", "value": 100}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "promotions.coupon.code_taken"


async def test_version_conflict_409(
    admin_client: httpx.AsyncClient, new_code: Callable[[str], str]
) -> None:
    created = await create(admin_client, new_code("VER"))
    ok = await admin_client.patch(f"{BASE}/{created['id']}", json={"version": 1, "value": 20})
    assert ok.status_code == 200
    stale = await admin_client.patch(f"{BASE}/{created['id']}", json={"version": 1, "value": 30})
    assert stale.status_code == 409
    assert stale.json()["code"] == "promotions.coupon.version_conflict"


async def test_patch_code_is_immutable_422(
    admin_client: httpx.AsyncClient, new_code: Callable[[str], str]
) -> None:
    created = await create(admin_client, new_code("IMM"))
    response = await admin_client.patch(
        f"{BASE}/{created['id']}", json={"version": 1, "code": "OUTRO"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "promotions.coupon.code_immutable"


async def test_patch_revalidates_merged_state(
    admin_client: httpx.AsyncClient, new_code: Callable[[str], str]
) -> None:
    created = await create(admin_client, new_code("MRG"))
    response = await admin_client.patch(f"{BASE}/{created['id']}", json={"version": 1, "value": 95})
    assert response.status_code == 422
    assert response.json()["code"] == "request.validation"
    assert "body.value" in response.json()["errors"]
    switched = await admin_client.patch(
        f"{BASE}/{created['id']}", json={"version": 1, "kind": "fixed", "value": 2500}
    )
    assert switched.status_code == 200
    assert switched.json()["kind"] == "fixed"


async def test_patch_not_found_404(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.patch(f"{BASE}/{uuid.uuid7()}", json={"version": 1})
    assert response.status_code == 404
    assert response.json()["code"] == "promotions.coupon.not_found"


async def test_delete_blocked_by_redemptions(
    admin_client: httpx.AsyncClient,
    new_code: Callable[[str], str],
    redeem: Callable[..., Awaitable[None]],
) -> None:
    created = await create(admin_client, new_code("RED"))
    await redeem(created["id"])
    fetched = await admin_client.get(f"{BASE}/{created['id']}")
    assert fetched.json()["uses_count"] == 1
    response = await admin_client.delete(f"{BASE}/{created['id']}")
    assert response.status_code == 409
    assert response.json()["code"] == "promotions.coupon.has_redemptions"


async def test_activate_and_deactivate(
    admin_client: httpx.AsyncClient, new_code: Callable[[str], str]
) -> None:
    created = await create(admin_client, new_code("ACT"), active=False)
    assert created["active"] is False
    on = await admin_client.post(f"{BASE}/{created['id']}/activate")
    assert on.status_code == 200
    assert on.json()["active"] is True
    assert on.json()["version"] == 2
    off = await admin_client.post(f"{BASE}/{created['id']}/deactivate")
    assert off.json()["active"] is False
    assert off.json()["version"] == 3


async def test_list_filters_and_pagination(admin_client: httpx.AsyncClient) -> None:
    tag = uuid.uuid7().hex[-8:].upper()
    codes = [f"LIST{tag}-{n}" for n in range(3)]
    for index, code in enumerate(codes):
        await create(admin_client, code, active=index != 0)
    page1 = await admin_client.get(BASE, params={"q": f"list{tag}", "limit": 2})
    assert page1.status_code == 200
    data = page1.json()
    assert [c["code"] for c in data["items"]] == [codes[2], codes[1]]
    assert data["next_cursor"] is not None
    page2 = await admin_client.get(
        BASE, params={"q": f"list{tag}", "limit": 2, "cursor": data["next_cursor"]}
    )
    assert [c["code"] for c in page2.json()["items"]] == [codes[0]]
    assert page2.json()["next_cursor"] is None
    active_only = await admin_client.get(BASE, params={"q": f"LIST{tag}", "active": "true"})
    assert [c["code"] for c in active_only.json()["items"]] == [codes[2], codes[1]]
    inactive = await admin_client.get(BASE, params={"q": f"LIST{tag}", "active": "false"})
    assert [c["code"] for c in inactive.json()["items"]] == [codes[0]]


async def test_list_invalid_cursor_422(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get(BASE, params={"cursor": "!!!"})
    assert response.status_code == 422
    assert response.json()["code"] == "promotions.pagination.invalid_cursor"


async def test_admin_create_rejects_bad_code_422(admin_client: httpx.AsyncClient) -> None:
    for bad in ["ab", "COD_IGO", "CÓDIGO", "x" * 33, ""]:
        response = await admin_client.post(BASE, json={"code": bad, "kind": "fixed", "value": 5})
        assert response.status_code == 422, bad
        assert response.json()["code"] == "request.validation"
        assert "body.code" in response.json()["errors"]


async def test_create_validation_rules(
    admin_client: httpx.AsyncClient, new_code: Callable[[str], str]
) -> None:
    cases: list[Json] = [
        {"kind": "percent", "value": 91},
        {"kind": "percent", "value": 0},
        {"kind": "fixed", "value": 0},
        {"kind": "bogus", "value": 5},
        {"min_order_cents": 0},
        {"max_uses_total": 0},
        {"max_uses_per_customer": 0},
        {"starts_at": "2026-12-02T00:00:00Z", "ends_at": "2026-12-01T00:00:00Z"},
        {"starts_at": "2026-12-01T00:00:00"},
        {"category_slugs": ["Not A Slug"]},
        {"collection_slugs": [f"c{n}" for n in range(51)]},
    ]
    for case in cases:
        payload = {"code": new_code("VAL"), "kind": "percent", "value": 10, **case}
        response = await admin_client.post(BASE, json=payload)
        assert response.status_code == 422, case
        assert response.json()["code"] == "request.validation", case


async def test_fixed_value_above_90_allowed(
    admin_client: httpx.AsyncClient, new_code: Callable[[str], str]
) -> None:
    created = await create(admin_client, new_code("FIX"), kind="fixed", value=5000)
    assert created["value"] == 5000


async def test_requires_admin_permission(
    client: httpx.AsyncClient,
    customer_token: str,
    service_token: str,
    staff_without_roles_token: str,
) -> None:
    assert (await client.get(BASE)).status_code == 401
    for token in (customer_token, service_token):
        response = await client.get(BASE, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403
    staff = await client.get(BASE, headers={"Authorization": f"Bearer {staff_without_roles_token}"})
    assert staff.status_code == 403
    assert staff.json()["code"] == "auth.insufficient_permission"
