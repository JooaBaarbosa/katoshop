"""Casos de uso do admin de cupons. Cada método roda numa transação própria."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from promotions.application.cursor import decode_cursor, encode_cursor, invalid_cursor
from promotions.application.ports import (
    CouponCursor,
    CouponFilter,
    CouponRecord,
    UnitOfWorkFactory,
)
from promotions.domain.fields import merged_errors

COUPON_NOT_FOUND = "promotions.coupon.not_found"
COUPON_CODE_TAKEN = "promotions.coupon.code_taken"
COUPON_VERSION_CONFLICT = "promotions.coupon.version_conflict"
COUPON_HAS_REDEMPTIONS = "promotions.coupon.has_redemptions"
COUPON_CODE_IMMUTABLE = "promotions.coupon.code_immutable"
REQUEST_VALIDATION = "request.validation"


class CouponError(Exception):
    def __init__(self, code: str, errors: dict[str, list[str]] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.errors = errors


def encode_coupon_cursor(coupon: CouponRecord) -> str:
    return encode_cursor({"c": coupon.created_at.isoformat(), "i": str(coupon.id)})


def decode_coupon_cursor(token: str) -> CouponCursor:
    payload = decode_cursor(token, ("c", "i"))
    try:
        created_at = datetime.fromisoformat(payload["c"])
        row_id = uuid.UUID(payload["i"])
    except ValueError as exc:
        raise invalid_cursor() from exc
    if created_at.tzinfo is None:
        raise invalid_cursor()
    return CouponCursor(created_at, row_id)


class AdminCouponService:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    async def list(
        self, filters: CouponFilter, cursor: str | None, limit: int
    ) -> tuple[list[CouponRecord], str | None]:
        position = decode_coupon_cursor(cursor) if cursor else None
        async with self._uow() as uow:
            rows = await uow.coupons.list(filters, position, limit + 1)
        page = rows[:limit]
        next_cursor = encode_coupon_cursor(page[-1]) if len(rows) > limit else None
        return page, next_cursor

    async def get(self, coupon_id: uuid.UUID) -> CouponRecord:
        async with self._uow() as uow:
            return await self._require(uow.coupons.get(coupon_id))

    async def create(self, fields: dict[str, Any]) -> CouponRecord:
        try:
            async with self._uow() as uow:
                if await uow.coupons.code_exists(fields["code"]):
                    raise CouponError(COUPON_CODE_TAKEN)
                return await uow.coupons.add(fields)
        except IntegrityError as exc:
            # Corrida entre duas criações do mesmo código: o índice único decide.
            if "ix_coupons_code" in str(exc.orig):
                raise CouponError(COUPON_CODE_TAKEN) from exc
            raise

    async def update(
        self, coupon_id: uuid.UUID, expected_version: int, changes: dict[str, Any]
    ) -> CouponRecord:
        async with self._uow() as uow:
            current = await self._require(uow.coupons.get(coupon_id))
            if current.version != expected_version:
                raise CouponError(COUPON_VERSION_CONFLICT)
            errors = merged_errors(current, changes)
            if errors:
                raise CouponError(REQUEST_VALIDATION, errors)
            if changes and not await uow.coupons.update_versioned(
                coupon_id, expected_version, changes
            ):
                raise CouponError(COUPON_VERSION_CONFLICT)
            return await self._require(uow.coupons.get(coupon_id))

    async def set_active(self, coupon_id: uuid.UUID, active: bool) -> CouponRecord:
        async with self._uow() as uow:
            current = await self._require(uow.coupons.get(coupon_id))
            if current.active != active and not await uow.coupons.update_versioned(
                coupon_id, current.version, {"active": active}
            ):
                raise CouponError(COUPON_VERSION_CONFLICT)
            return await self._require(uow.coupons.get(coupon_id))

    async def delete(self, coupon_id: uuid.UUID) -> None:
        async with self._uow() as uow:
            await self._require(uow.coupons.get(coupon_id))
            if await uow.coupons.count_uses(coupon_id) > 0:
                raise CouponError(COUPON_HAS_REDEMPTIONS)
            await uow.coupons.delete(coupon_id)

    @staticmethod
    async def _require(pending: Any) -> CouponRecord:
        record: CouponRecord | None = await pending
        if record is None:
            raise CouponError(COUPON_NOT_FOUND)
        return record
