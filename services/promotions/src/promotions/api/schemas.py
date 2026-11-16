import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from promotions.application.evaluate_service import EvaluationResult
from promotions.application.ports import CouponRecord
from promotions.domain.coupons import normalize_code
from promotions.domain.fields import cross_field_errors

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


Slugs = Annotated[list[Slug], Field(max_length=50), AfterValidator(_dedupe)]
PositiveInt = Annotated[int, Field(ge=1, le=2_000_000_000)]


def _code(value: str) -> str:
    try:
        return normalize_code(value)
    except ValueError as exc:
        raise ValueError("Código deve ter de 3 a 32 caracteres: A-Z, 0-9 e hífen") from exc


Code = Annotated[str, AfterValidator(_code)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CouponIn(_In):
    code: Code
    description: str = Field(default="", max_length=500)
    kind: Literal["percent", "fixed"]
    value: PositiveInt
    min_order_cents: PositiveInt | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    category_slugs: Slugs = Field(default_factory=list)
    collection_slugs: Slugs = Field(default_factory=list)
    max_uses_total: PositiveInt | None = None
    max_uses_per_customer: PositiveInt | None = None
    active: bool = True

    @model_validator(mode="after")
    def _cross_fields(self) -> Self:
        errors = cross_field_errors(self.kind, self.value, self.starts_at, self.ends_at)
        if errors:
            raise ValueError("; ".join(msg for msgs in errors.values() for msg in msgs))
        return self


class CouponPatch(BaseModel):
    """Os campos de CouponIn menos `code`, todos opcionais, mais `version`.

    `code` entra como campo extra só para a rota responder 422 `code_immutable`.
    """

    model_config = ConfigDict(extra="allow")

    version: int = Field(ge=1)
    description: str | None = Field(default=None, max_length=500)
    kind: Literal["percent", "fixed"] | None = None
    value: PositiveInt | None = None
    min_order_cents: PositiveInt | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    category_slugs: Slugs | None = None
    collection_slugs: Slugs | None = None
    max_uses_total: PositiveInt | None = None
    max_uses_per_customer: PositiveInt | None = None
    active: bool | None = None

    @field_validator("description", "kind", "value", "category_slugs", "collection_slugs", "active")
    @classmethod
    def _not_null(cls, value: object) -> object:
        # Só limites e datas podem ser limpos com null; os demais campos são obrigatórios.
        if value is None:
            raise ValueError("não pode ser nulo")
        return value

    def changes(self) -> dict[str, object]:
        return {
            name: getattr(self, name)
            for name in self.model_fields_set
            if name in type(self).model_fields and name != "version"
        }

    @property
    def sends_code(self) -> bool:
        return "code" in (self.model_extra or {})


class CouponOut(BaseModel):
    id: uuid.UUID
    code: str
    description: str
    kind: Literal["percent", "fixed"]
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

    @classmethod
    def from_record(cls, c: CouponRecord) -> Self:
        return cls.model_validate(c, from_attributes=True)


class CouponPage(BaseModel):
    items: list[CouponOut]
    next_cursor: str | None


class EvaluateItem(_In):
    variant_id: uuid.UUID
    unit_price_cents: int = Field(ge=0, le=2_000_000_000)
    quantity: int = Field(ge=1, le=1000)
    category_slug: str = Field(max_length=120)
    collection_slugs: list[str] = Field(default_factory=list, max_length=50)


class EvaluateIn(_In):
    code: str = Field(max_length=200)
    customer_id: uuid.UUID | None = None
    items: Annotated[list[EvaluateItem], Field(min_length=1, max_length=50)]

    @field_validator("items")
    @classmethod
    def _unique_variants(cls, items: list[EvaluateItem]) -> list[EvaluateItem]:
        if len({i.variant_id for i in items}) != len(items):
            raise ValueError("variant_id repetido")
        return items


class PerItemDiscount(BaseModel):
    variant_id: uuid.UUID
    discount_cents: int


class EvaluateOut(BaseModel):
    valid: bool
    code: str
    discount_cents: int
    per_item: list[PerItemDiscount]
    reason: str | None
    min_order_cents: int | None

    @classmethod
    def from_result(cls, result: EvaluationResult) -> Self:
        ev = result.evaluation
        return cls(
            valid=ev.valid,
            code=result.code,
            discount_cents=ev.discount_cents,
            per_item=[
                PerItemDiscount(
                    variant_id=uuid.UUID(i.variant_id), discount_cents=ev.per_item[i.variant_id]
                )
                for i in result.items
                if i.variant_id in ev.per_item
            ],
            reason=ev.reason,
            min_order_cents=ev.min_order_cents,
        )
