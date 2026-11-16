import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class CouponRecord:
    id: uuid.UUID
    code: str
    description: str
    kind: str
    value: int
    min_order_cents: int | None
    starts_at: datetime | None
    ends_at: datetime | None
    category_slugs: list[str]
    collection_slugs: list[str]
    max_uses_total: int | None
    max_uses_per_customer: int | None
    active: bool
    version: int
    created_at: datetime
    updated_at: datetime
    uses_count: int


@dataclass(frozen=True)
class CouponCursor:
    created_at: datetime
    id: uuid.UUID


@dataclass(frozen=True)
class CouponFilter:
    q: str | None = None
    active: bool | None = None


class CouponRepository(Protocol):
    async def add(self, fields: dict[str, Any]) -> CouponRecord: ...

    async def get(self, coupon_id: uuid.UUID) -> CouponRecord | None: ...

    async def get_by_code(self, code: str) -> CouponRecord | None: ...

    async def code_exists(self, code: str) -> bool: ...

    async def list(
        self, filters: CouponFilter, cursor: CouponCursor | None, limit: int
    ) -> list[CouponRecord]: ...

    async def update_versioned(
        self, coupon_id: uuid.UUID, expected_version: int, fields: dict[str, Any]
    ) -> bool: ...

    async def delete(self, coupon_id: uuid.UUID) -> None: ...

    async def count_uses(
        self, coupon_id: uuid.UUID, customer_id: uuid.UUID | None = None
    ) -> int: ...


class PromotionsUnitOfWork(Protocol):
    @property
    def coupons(self) -> CouponRepository: ...


type UnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[PromotionsUnitOfWork]]
