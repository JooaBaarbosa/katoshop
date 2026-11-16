import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from ks_platform.auth import require_permission
from ks_platform.errors import ProblemError
from promotions.api.errors import mapped
from promotions.api.schemas import CouponIn, CouponOut, CouponPage, CouponPatch
from promotions.application.admin_service import COUPON_CODE_IMMUTABLE, AdminCouponService
from promotions.application.ports import CouponFilter

router = APIRouter(
    prefix="/v1/admin/coupons",
    tags=["admin"],
    dependencies=[Depends(require_permission("promotions.write"))],
)

Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=512)]


def admin_service(request: Request) -> AdminCouponService:
    service: AdminCouponService = request.app.state.admin_service
    return service


Service = Annotated[AdminCouponService, Depends(admin_service)]


@router.get("")
async def list_coupons(
    service: Service,
    q: Annotated[str | None, Query(max_length=200)] = None,
    active: bool | None = None,
    cursor: Cursor = None,
    limit: Limit = 24,
) -> CouponPage:
    rows, next_cursor = await mapped(service.list(CouponFilter(q=q, active=active), cursor, limit))
    return CouponPage(items=[CouponOut.from_record(r) for r in rows], next_cursor=next_cursor)


@router.post("", status_code=201)
async def create_coupon(body: CouponIn, service: Service) -> CouponOut:
    created = await mapped(service.create(body.model_dump()))
    return CouponOut.from_record(created)


@router.get("/{coupon_id}")
async def get_coupon(coupon_id: uuid.UUID, service: Service) -> CouponOut:
    return CouponOut.from_record(await mapped(service.get(coupon_id)))


@router.patch("/{coupon_id}")
async def update_coupon(coupon_id: uuid.UUID, body: CouponPatch, service: Service) -> CouponOut:
    if body.sends_code:
        raise ProblemError(422, COUPON_CODE_IMMUTABLE, "O código do cupom não pode ser alterado")
    updated = await mapped(service.update(coupon_id, body.version, body.changes()))
    return CouponOut.from_record(updated)


@router.post("/{coupon_id}/activate")
async def activate_coupon(coupon_id: uuid.UUID, service: Service) -> CouponOut:
    return CouponOut.from_record(await mapped(service.set_active(coupon_id, True)))


@router.post("/{coupon_id}/deactivate")
async def deactivate_coupon(coupon_id: uuid.UUID, service: Service) -> CouponOut:
    return CouponOut.from_record(await mapped(service.set_active(coupon_id, False)))


@router.delete("/{coupon_id}", status_code=204)
async def delete_coupon(coupon_id: uuid.UUID, service: Service) -> Response:
    await mapped(service.delete(coupon_id))
    return Response(status_code=204)
