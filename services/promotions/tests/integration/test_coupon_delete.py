import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from promotions.application.admin_service import (
    FK_VIOLATIONS,
    REDEMPTIONS_FK,
    AdminCouponService,
    CouponError,
    violates_constraint,
)


class _FkOrig(Exception):
    sqlstate = "23001"
    constraint_name = REDEMPTIONS_FK


class _FakeCoupons:
    async def lock(self, _coupon_id: uuid.UUID) -> bool:
        return True

    async def count_uses(self, _coupon_id: uuid.UUID, _customer: uuid.UUID | None = None) -> int:
        return 0

    async def delete(self, _coupon_id: uuid.UUID) -> None:
        raise IntegrityError("DELETE", {}, _FkOrig())


class _FakeUow:
    coupons = _FakeCoupons()


@asynccontextmanager
async def _fake_uow() -> AsyncIterator[Any]:
    yield _FakeUow()


async def test_fk_violation_on_delete_maps_to_has_redemptions() -> None:
    service = AdminCouponService(_fake_uow)
    with pytest.raises(CouponError) as caught:
        await service.delete(uuid.uuid4())
    assert caught.value.code == "promotions.coupon.has_redemptions"


async def test_real_driver_exposes_sqlstate_and_constraint_name(
    app: FastAPI, admin_client: httpx.AsyncClient, redeem: Callable[..., Awaitable[None]]
) -> None:
    created = await admin_client.post(
        "/v1/admin/coupons",
        json={"code": f"FK-{uuid.uuid7().hex[-10:].upper()}", "kind": "fixed", "value": 5},
    )
    coupon_id = created.json()["id"]
    await redeem(coupon_id)
    with pytest.raises(IntegrityError) as caught:
        async with app.state.session_factory() as session, session.begin():
            await session.execute(text("DELETE FROM coupons WHERE id = :i"), {"i": coupon_id})
    assert getattr(caught.value.orig, "sqlstate", None) in FK_VIOLATIONS
    assert violates_constraint(caught.value, FK_VIOLATIONS, REDEMPTIONS_FK)
    assert not violates_constraint(caught.value, FK_VIOLATIONS, "outra_constraint")


async def test_delete_waits_for_concurrent_redemption_and_answers_409(
    app: FastAPI, admin_client: httpx.AsyncClient
) -> None:
    created = await admin_client.post(
        "/v1/admin/coupons",
        json={"code": f"RC-{uuid.uuid7().hex[-10:].upper()}", "kind": "fixed", "value": 5},
    )
    coupon_id = created.json()["id"]
    async with app.state.session_factory() as session, session.begin():
        # Resgate ainda não confirmado: segura FOR KEY SHARE na linha do cupom.
        await session.execute(
            text(
                "INSERT INTO coupon_redemptions (id, coupon_id, customer_id, order_id) "
                "VALUES (:id, :c, :cu, :o)"
            ),
            {"id": uuid.uuid4(), "c": coupon_id, "cu": uuid.uuid4(), "o": uuid.uuid4()},
        )
        pending = asyncio.create_task(admin_client.delete(f"/v1/admin/coupons/{coupon_id}"))
        await asyncio.sleep(0.5)
        assert not pending.done()
    response = await asyncio.wait_for(pending, timeout=10)
    assert response.status_code == 409
    assert response.json()["code"] == "promotions.coupon.has_redemptions"
