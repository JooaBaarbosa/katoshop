import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import ColumnElement, and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from promotions.adapters.models import Coupon, CouponRedemption
from promotions.application.ports import (
    CouponCursor,
    CouponFilter,
    CouponRecord,
    PromotionsUnitOfWork,
    UnitOfWorkFactory,
)

_NO_SYNC = {"synchronize_session": False}

_USES = (
    select(func.count())
    .where(CouponRedemption.coupon_id == Coupon.id)
    .correlate(Coupon)
    .scalar_subquery()
)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _record(coupon: Coupon, uses_count: int) -> CouponRecord:
    return CouponRecord(
        id=coupon.id,
        code=coupon.code,
        description=coupon.description,
        kind=coupon.kind,
        value=coupon.value,
        min_order_cents=coupon.min_order_cents,
        starts_at=coupon.starts_at,
        ends_at=coupon.ends_at,
        category_slugs=list(coupon.category_slugs),
        collection_slugs=list(coupon.collection_slugs),
        max_uses_total=coupon.max_uses_total,
        max_uses_per_customer=coupon.max_uses_per_customer,
        active=coupon.active,
        version=coupon.version,
        created_at=coupon.created_at,
        updated_at=coupon.updated_at,
        uses_count=uses_count,
    )


class SqlCouponRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _one(self, where: ColumnElement[bool]) -> CouponRecord | None:
        row = (
            await self._s.execute(
                select(Coupon, _USES).where(where).execution_options(populate_existing=True)
            )
        ).first()
        return _record(row[0], row[1]) if row else None

    async def add(self, fields: dict[str, Any]) -> CouponRecord:
        coupon = Coupon(**fields)
        self._s.add(coupon)
        await self._s.flush()
        await self._s.refresh(coupon)
        return _record(coupon, 0)

    async def get(self, coupon_id: uuid.UUID) -> CouponRecord | None:
        return await self._one(Coupon.id == coupon_id)

    async def get_by_code(self, code: str) -> CouponRecord | None:
        return await self._one(Coupon.code == code)

    async def code_exists(self, code: str) -> bool:
        return await self._s.scalar(select(Coupon.id).where(Coupon.code == code)) is not None

    async def list(
        self, filters: CouponFilter, cursor: CouponCursor | None, limit: int
    ) -> list[CouponRecord]:
        stmt = select(Coupon, _USES)
        if filters.q:
            stmt = stmt.where(
                or_(
                    Coupon.code.ilike(f"%{_escape_like(filters.q)}%", escape="\\"),
                    Coupon.description.ilike(f"%{_escape_like(filters.q)}%", escape="\\"),
                )
            )
        if filters.active is not None:
            stmt = stmt.where(Coupon.active.is_(filters.active))
        if cursor is not None:
            stmt = stmt.where(
                or_(
                    Coupon.created_at < cursor.created_at,
                    and_(Coupon.created_at == cursor.created_at, Coupon.id < cursor.id),
                )
            )
        stmt = stmt.order_by(Coupon.created_at.desc(), Coupon.id.desc()).limit(limit)
        return [_record(c, uses) for c, uses in (await self._s.execute(stmt)).all()]

    async def update_versioned(
        self, coupon_id: uuid.UUID, expected_version: int, fields: dict[str, Any]
    ) -> bool:
        stmt = (
            update(Coupon)
            .where(Coupon.id == coupon_id, Coupon.version == expected_version)
            .values(**fields, version=Coupon.version + 1, updated_at=func.now())
            .returning(Coupon.id)
        )
        return await self._s.scalar(stmt.execution_options(**_NO_SYNC)) is not None

    async def delete(self, coupon_id: uuid.UUID) -> None:
        await self._s.execute(
            delete(Coupon).where(Coupon.id == coupon_id).execution_options(**_NO_SYNC)
        )

    async def count_uses(self, coupon_id: uuid.UUID, customer_id: uuid.UUID | None = None) -> int:
        stmt = select(func.count()).where(CouponRedemption.coupon_id == coupon_id)
        if customer_id is not None:
            stmt = stmt.where(CouponRedemption.customer_id == customer_id)
        return int(await self._s.scalar(stmt) or 0)


class SqlPromotionsUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._coupons = SqlCouponRepository(session)

    @property
    def coupons(self) -> SqlCouponRepository:
        return self._coupons


def sql_unit_of_work(session_factory: async_sessionmaker[AsyncSession]) -> UnitOfWorkFactory:
    """Cada chamada abre uma sessão e uma transação próprias (commit ao sair sem erro)."""

    @asynccontextmanager
    async def open_uow() -> AsyncIterator[PromotionsUnitOfWork]:
        async with session_factory() as session, session.begin():
            yield SqlPromotionsUnitOfWork(session)

    return open_uow
