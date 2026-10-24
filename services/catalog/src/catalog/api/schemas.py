import uuid
from datetime import datetime
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from catalog.application.ports import (
    CategoryRecord,
    CollectionRecord,
    ImageRecord,
    MovementRecord,
    Overview,
    ProductRecord,
    ProductRow,
    RecentMovement,
    VariantRecord,
)
from catalog.domain.stock import available, effective_price

Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=120)]
ProductSlug = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=160)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Cents = Annotated[int, Field(ge=0, le=100_000_000)]
Position = Annotated[int, Field(ge=0, le=100_000)]
OptionCode = Annotated[str, Field(min_length=1, max_length=8)]
ProductStatus = Literal["draft", "active", "archived"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Patch(_In):
    """PATCH parcial: só os campos enviados mudam; `null` só vale para campos anuláveis."""

    nullable: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_nulls(self) -> Self:
        for name in self.model_fields_set:
            if getattr(self, name) is None and name not in self.nullable:
                raise ValueError(f"{name} não pode ser nulo")
        return self

    def changes(self, *, exclude: frozenset[str] = frozenset()) -> dict[str, Any]:
        return self.model_dump(include=self.model_fields_set - exclude)


# ---------------------------------------------------------------------------- categorias


class CategoryIn(_In):
    name: Name
    slug: Slug | None = None
    parent_id: uuid.UUID | None = None
    position: Position = 0


class CategoryPatch(_Patch):
    nullable: ClassVar[frozenset[str]] = frozenset({"parent_id"})

    name: Name | None = None
    slug: Slug | None = None
    parent_id: uuid.UUID | None = None
    position: Position | None = None


class CategoryRef(BaseModel):
    id: uuid.UUID
    slug: str
    name: str

    @classmethod
    def from_record(cls, c: CategoryRecord) -> CategoryRef:
        return cls(id=c.id, slug=c.slug, name=c.name)


class CategoryOut(CategoryRef):
    parent_id: uuid.UUID | None
    position: int

    @classmethod
    def from_record(cls, c: CategoryRecord) -> CategoryOut:
        return cls(id=c.id, slug=c.slug, name=c.name, parent_id=c.parent_id, position=c.position)


class CategoryList(BaseModel):
    items: list[CategoryOut]


# ---------------------------------------------------------------------------- coleções


class CollectionIn(_In):
    name: Name
    slug: Slug | None = None
    description: str | None = Field(default=None, max_length=2000)
    featured: bool = False
    position: Position = 0


class CollectionPatch(_Patch):
    nullable: ClassVar[frozenset[str]] = frozenset({"description"})

    name: Name | None = None
    slug: Slug | None = None
    description: str | None = Field(default=None, max_length=2000)
    featured: bool | None = None
    position: Position | None = None


class CollectionProductsIn(_In):
    product_ids: list[uuid.UUID] = Field(max_length=500)


class CollectionOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    featured: bool
    position: int
    product_ids: list[uuid.UUID]

    @classmethod
    def from_record(cls, c: CollectionRecord) -> CollectionOut:
        return cls(
            id=c.id,
            slug=c.slug,
            name=c.name,
            description=c.description,
            featured=c.featured,
            position=c.position,
            product_ids=c.product_ids,
        )


class CollectionList(BaseModel):
    items: list[CollectionOut]


# ---------------------------------------------------------------------------- produtos


class ProductIn(_In):
    name: Name
    slug: ProductSlug | None = None
    description: str | None = Field(default=None, max_length=5000)
    category_id: uuid.UUID
    base_price_cents: Cents
    attributes: dict[str, Any] = Field(default_factory=dict)


class ProductPatch(_Patch):
    nullable: ClassVar[frozenset[str]] = frozenset({"description"})

    version: int
    name: Name | None = None
    slug: ProductSlug | None = None
    description: str | None = Field(default=None, max_length=5000)
    category_id: uuid.UUID | None = None
    base_price_cents: Cents | None = None
    attributes: dict[str, Any] | None = None


class GenerateVariantsIn(_In):
    colors: list[OptionCode] = Field(min_length=1, max_length=20)
    sizes: list[OptionCode] = Field(min_length=1, max_length=20)


class VariantPatch(_Patch):
    nullable: ClassVar[frozenset[str]] = frozenset({"price_cents"})

    version: int
    price_cents: Cents | None = None
    active: bool | None = None


class AdminVariant(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    sku: str
    color_code: str
    size_code: str
    price_cents: int | None
    stock_on_hand: int
    stock_reserved: int
    available: int
    version: int
    active: bool


class AdminVariantWithPrice(AdminVariant):
    effective_price_cents: int


ImageAlt = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
ImageText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
ImageSourceUrl = Annotated[str, Field(max_length=2000, pattern=r"^https?://\S+$")]


class ImageUploadIn(_In):
    """Campos de texto do multipart; `alt` é validado antes, com código próprio."""

    color_code: OptionCode | None = None
    credit_author: ImageText | None = None
    credit_source_url: ImageSourceUrl | None = None
    license: ImageText | None = None


class ImagePatch(_Patch):
    nullable: ClassVar[frozenset[str]] = frozenset(
        {"color_code", "credit_author", "credit_source_url", "license"}
    )

    alt: ImageAlt | None = None
    color_code: OptionCode | None = None
    position: Annotated[int, Field(ge=0, le=1000)] | None = None
    credit_author: ImageText | None = None
    credit_source_url: ImageSourceUrl | None = None
    license: ImageText | None = None


def media_url(public_base_url: str, key: str) -> str:
    return f"{public_base_url.rstrip('/')}/v1/media/{key}"


class AdminImage(BaseModel):
    id: uuid.UUID
    color_code: str | None
    storage_key: str
    width: int
    height: int
    alt: str
    position: int
    credit_author: str | None
    credit_source_url: str | None
    license: str | None
    url: str

    @classmethod
    def from_record(cls, i: ImageRecord, public_base_url: str) -> AdminImage:
        return cls(
            id=i.id,
            url=media_url(public_base_url, i.storage_key),
            color_code=i.color_code,
            storage_key=i.storage_key,
            width=i.width,
            height=i.height,
            alt=i.alt,
            position=i.position,
            credit_author=i.credit_author,
            credit_source_url=i.credit_source_url,
            license=i.license,
        )


def variant_out(v: VariantRecord) -> AdminVariant:
    return AdminVariant(
        id=v.id,
        product_id=v.product_id,
        sku=v.sku,
        color_code=v.color_code,
        size_code=v.size_code,
        price_cents=v.price_cents,
        stock_on_hand=v.stock_on_hand,
        stock_reserved=v.stock_reserved,
        available=available(v.stock_on_hand, v.stock_reserved),
        version=v.version,
        active=v.active,
    )


class AdminProduct(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    category_id: uuid.UUID
    category: CategoryRef
    status: ProductStatus
    base_price_cents: int
    min_price_cents: int | None
    attributes: dict[str, Any]
    version: int
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    variants: list[AdminVariantWithPrice]
    images: list[AdminImage]

    @classmethod
    def from_record(cls, p: ProductRecord, public_base_url: str) -> AdminProduct:
        return cls(
            id=p.id,
            slug=p.slug,
            name=p.name,
            description=p.description,
            category_id=p.category.id,
            category=CategoryRef.from_record(p.category),
            status=p.status,  # pyright: ignore[reportArgumentType]
            base_price_cents=p.base_price_cents,
            min_price_cents=p.min_price_cents,
            attributes=p.attributes,
            version=p.version,
            published_at=p.published_at,
            created_at=p.created_at,
            updated_at=p.updated_at,
            variants=[
                AdminVariantWithPrice(
                    **variant_out(v).model_dump(),
                    effective_price_cents=effective_price(p.base_price_cents, v.price_cents),
                )
                for v in p.variants
            ],
            images=[AdminImage.from_record(i, public_base_url) for i in p.images],
        )


class AdminProductRow(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: ProductStatus
    category: CategoryRef
    min_price_cents: int | None
    variant_count: int
    total_available: int
    updated_at: datetime

    @classmethod
    def from_record(cls, r: ProductRow) -> AdminProductRow:
        return cls(
            id=r.id,
            slug=r.slug,
            name=r.name,
            status=r.status,  # pyright: ignore[reportArgumentType]
            category=CategoryRef.from_record(r.category),
            min_price_cents=r.min_price_cents,
            variant_count=r.variant_count,
            total_available=r.total_available,
            updated_at=r.updated_at,
        )


class ProductPage(BaseModel):
    items: list[AdminProductRow]
    next_cursor: str | None


# ---------------------------------------------------------------------------- estoque


class StockAdjustmentIn(_In):
    delta: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(max_length=16)
    note: str | None = Field(default=None, max_length=500)


class MovementOut(BaseModel):
    id: uuid.UUID
    variant_id: uuid.UUID
    delta: int
    reason: str
    note: str | None
    actor_id: uuid.UUID | None
    created_at: datetime

    @classmethod
    def from_record(cls, m: MovementRecord) -> MovementOut:
        return cls(
            id=m.id,
            variant_id=m.variant_id,
            delta=m.delta,
            reason=m.reason,
            note=m.note,
            actor_id=m.actor_id,
            created_at=m.created_at,
        )


class StockAdjustmentOut(BaseModel):
    movement: MovementOut
    variant: AdminVariant


class MovementPage(BaseModel):
    items: list[MovementOut]
    next_cursor: str | None


class RecentMovementOut(MovementOut):
    sku: str
    product_id: uuid.UUID
    product_name: str

    @classmethod
    def from_recent(cls, r: RecentMovement) -> RecentMovementOut:
        return cls(
            **MovementOut.from_record(r.movement).model_dump(),
            sku=r.sku,
            product_id=r.product_id,
            product_name=r.product_name,
        )


class ProductsByStatus(BaseModel):
    draft: int
    active: int
    archived: int


class OverviewOut(BaseModel):
    products_by_status: ProductsByStatus
    out_of_stock_variants: int
    recent_movements: list[RecentMovementOut]

    @classmethod
    def from_overview(cls, o: Overview) -> OverviewOut:
        return cls(
            products_by_status=ProductsByStatus(**o.products_by_status),
            out_of_stock_variants=o.out_of_stock_variants,
            recent_movements=[RecentMovementOut.from_recent(r) for r in o.recent_movements],
        )
