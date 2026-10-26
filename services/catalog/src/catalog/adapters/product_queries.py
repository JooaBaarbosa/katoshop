"""Leituras públicas do catálogo (SQLAlchemy Core): listagem, busca, facetas, detalhe, créditos.

Só produtos `active` com pelo menos uma variante ativa aparecem. "Disponível" é sempre
`stock_on_hand - stock_reserved > 0` numa variante ativa.
"""

import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import (
    ColumnElement,
    Double,
    and_,
    cast,
    distinct,
    exists,
    func,
    literal,
    literal_column,
    select,
    tuple_,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from catalog.adapters.models import (
    Category,
    Collection,
    CollectionProduct,
    Color,
    Product,
    ProductImage,
    Size,
    Variant,
)
from catalog.application.cursor import decode_cursor, encode_cursor, invalid_cursor
from catalog.domain.stock import available, effective_price
from ks_platform.errors import ProblemError

SortOrder = Literal["relevance", "newest", "price_asc", "price_desc"]

MAX_QUERY_LENGTH = 200
QUERY_TOO_LONG = "catalog.search.query_too_long"
_INT4_MAX = 2**31 - 1
_PRICE_KEY_RE = re.compile(r"^[0-9]{1,10}$")
_CURSOR_KEYS = ("s", "k", "id")
# Constante do código, nunca entrada do usuário.
_TS_CONFIG = literal_column("'portuguese'::regconfig")


@dataclass(frozen=True)
class ProductFilter:
    category: str | None
    collection: str | None
    sizes: tuple[str, ...]
    colors: tuple[str, ...]
    price_min: int | None
    price_max: int | None
    q: str | None
    sort: SortOrder

    def __post_init__(self) -> None:
        q = (self.q or "").strip() or None
        if q is not None and len(q) > MAX_QUERY_LENGTH:
            raise ProblemError(422, QUERY_TOO_LONG, "Busca com mais de 200 caracteres")
        object.__setattr__(self, "q", q)
        if self.sort == "relevance" and q is None:
            object.__setattr__(self, "sort", "newest")
        if (
            self.price_min is not None
            and self.price_max is not None
            and self.price_min > self.price_max
        ):
            raise ProblemError(
                422,
                "request.validation",
                "Requisição inválida",
                errors={"price_min": ["price_min maior que price_max"]},
            )


# ---------------------------------------------------------------------------- registros


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    next_cursor: str | None


@dataclass(frozen=True)
class ColorRef:
    code: str
    name: str
    hex: str


@dataclass(frozen=True)
class SizeRef:
    code: str
    label: str


@dataclass(frozen=True)
class CardImage:
    storage_key: str
    alt: str


@dataclass(frozen=True)
class ProductCard:
    slug: str
    name: str
    min_price_cents: int
    image: CardImage | None
    colors: list[ColorRef]
    sold_out: bool


@dataclass(frozen=True)
class SizeFacet:
    code: str
    label: str
    count: int


@dataclass(frozen=True)
class ColorFacet:
    code: str
    name: str
    hex: str
    count: int


@dataclass(frozen=True)
class CategoryFacet:
    slug: str
    name: str
    count: int


@dataclass(frozen=True)
class PriceRange:
    min: int | None
    max: int | None


@dataclass(frozen=True)
class Facets:
    sizes: list[SizeFacet]
    colors: list[ColorFacet]
    categories: list[CategoryFacet]
    price: PriceRange


@dataclass(frozen=True)
class PublicVariant:
    sku: str
    color_code: str
    size_code: str
    price_cents: int
    available: bool


@dataclass(frozen=True)
class PublicImage:
    storage_key: str
    alt: str
    color_code: str | None
    width: int
    height: int
    credit_author: str | None
    credit_source_url: str | None
    license: str | None


@dataclass(frozen=True)
class ProductDetail:
    slug: str
    name: str
    description: str | None
    attributes: dict[str, Any]
    category_slug: str
    category_name: str
    min_price_cents: int
    colors: list[ColorRef]
    sizes: list[SizeRef]
    variants: list[PublicVariant]
    images: list[PublicImage]


@dataclass(frozen=True)
class Credit:
    product_name: str
    storage_key: str
    credit_author: str | None
    credit_source_url: str | None
    license: str | None


# ---------------------------------------------------------------------------- filtros


def _tsquery(q: str) -> ColumnElement[Any]:
    # websearch_to_tsquery tolera operadores soltos e aspas; o texto vai como parâmetro.
    return func.websearch_to_tsquery(_TS_CONFIG, func.immutable_unaccent(q))


def _in_stock(v: Any) -> ColumnElement[bool]:
    return and_(v.active.is_(True), v.stock_on_hand - v.stock_reserved > 0)


def _variant_exists(
    sizes: tuple[str, ...], colors: tuple[str, ...], *, in_stock: bool
) -> ColumnElement[bool]:
    conditions: list[ColumnElement[bool]] = [
        Variant.product_id == Product.id,
        Variant.active.is_(True),
    ]
    if in_stock:
        conditions.append(_in_stock(Variant))
    if sizes:
        conditions.append(Variant.size_code.in_(sizes))
    if colors:
        conditions.append(Variant.color_code.in_(colors))
    return exists().where(*conditions)


Dimension = Literal["sizes", "colors", "category", "price"]


def _conditions(f: ProductFilter, skip: Dimension | None = None) -> list[ColumnElement[bool]]:
    """Condições de vitrine e de filtro; `skip` omite uma dimensão (facetas multisseleção)."""
    conditions: list[ColumnElement[bool]] = [
        Product.status == "active",
        Product.published_at.is_not(None),
        Product.min_price_cents.is_not(None),
        _variant_exists((), (), in_stock=False),
    ]
    if f.category is not None and skip != "category":
        conditions.append(
            Product.category_id.in_(select(Category.id).where(Category.slug == f.category))
        )
    if f.collection is not None:
        conditions.append(
            exists().where(
                CollectionProduct.product_id == Product.id,
                CollectionProduct.collection_id == Collection.id,
                Collection.slug == f.collection,
            )
        )
    sizes = () if skip == "sizes" else f.sizes
    colors = () if skip == "colors" else f.colors
    if sizes or colors:
        conditions.append(_variant_exists(sizes, colors, in_stock=True))
    if skip != "price":
        if f.price_min is not None:
            conditions.append(Product.min_price_cents >= f.price_min)
        if f.price_max is not None:
            conditions.append(Product.min_price_cents <= f.price_max)
    if f.q is not None:
        conditions.append(Product.search_vector.op("@@")(_tsquery(f.q)))
    return conditions


# ---------------------------------------------------------------------------- cursor

type SortKey = datetime | int | float


def _encode_key(sort: SortOrder, key: SortKey, product_id: uuid.UUID) -> str:
    # relevance: repr(float) volta exatamente ao mesmo double com float().
    text = key.isoformat() if isinstance(key, datetime) else repr(key)
    return encode_cursor({"s": sort, "k": text, "id": str(product_id)})


def _decode_key(raw: str, sort: SortOrder) -> tuple[SortKey, uuid.UUID]:
    payload = decode_cursor(raw, _CURSOR_KEYS)
    if payload["s"] != sort:
        raise invalid_cursor()
    text = payload["k"]
    try:
        product_id = uuid.UUID(payload["id"])
        key: SortKey
        if sort == "newest":
            key = datetime.fromisoformat(text)
            if key.tzinfo is None:
                raise invalid_cursor()
        elif sort == "relevance":
            key = float(text)
            if not math.isfinite(key):
                raise invalid_cursor()
        else:
            if not _PRICE_KEY_RE.fullmatch(text) or int(text) > _INT4_MAX:
                raise invalid_cursor()
            key = int(text)
    except ValueError as exc:
        raise invalid_cursor() from exc
    return key, product_id


# ---------------------------------------------------------------------------- listagem


def _sort_column(f: ProductFilter) -> tuple[ColumnElement[Any], bool]:
    """Coluna de ordenação e se é decrescente; o desempate é sempre `id` no mesmo sentido."""
    if f.sort == "relevance" and f.q is not None:
        return cast(func.ts_rank_cd(Product.search_vector, _tsquery(f.q)), Double), True
    if f.sort == "price_asc":
        return Product.min_price_cents.expression, False
    if f.sort == "price_desc":
        return Product.min_price_cents.expression, True
    return Product.published_at.expression, True


async def list_products(
    session: AsyncSession, f: ProductFilter, cursor: str | None, limit: int
) -> Page[ProductCard]:
    position = _decode_key(cursor, f.sort) if cursor else None
    sold_out = ~_variant_exists((), (), in_stock=True)
    sort_col, descending = _sort_column(f)
    conditions = _conditions(f)
    if position is not None:
        key, last_id = position
        here = tuple_(sort_col, Product.id)
        there = tuple_(literal(key, sort_col.type), literal(last_id, PG_UUID(as_uuid=True)))
        conditions.append(here < there if descending else here > there)
    order = (
        [sort_col.desc(), Product.id.desc()] if descending else [sort_col.asc(), Product.id.asc()]
    )
    stmt = (
        select(
            Product.id,
            Product.slug,
            Product.name,
            Product.min_price_cents,
            sold_out.label("sold_out"),
            sort_col.label("sort_key"),
        )
        .where(*conditions)
        .order_by(*order)
        .limit(limit + 1)
    )
    rows = (await session.execute(stmt)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    ids = [row.id for row in rows]
    images = await _first_images(session, ids)
    colors = await _colors_by_product(session, ids)
    cards = [
        ProductCard(
            slug=row.slug,
            name=row.name,
            min_price_cents=row.min_price_cents,
            image=images.get(row.id),
            colors=colors.get(row.id, []),
            sold_out=bool(row.sold_out),
        )
        for row in rows
    ]
    next_cursor = _encode_key(f.sort, rows[-1].sort_key, rows[-1].id) if more else None
    return Page(cards, next_cursor)


async def _first_images(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, CardImage]:
    if not ids:
        return {}
    stmt = (
        select(ProductImage.product_id, ProductImage.storage_key, ProductImage.alt)
        .where(ProductImage.product_id.in_(ids))
        .ext(distinct_on(ProductImage.product_id))
        .order_by(ProductImage.product_id, ProductImage.position, ProductImage.id)
    )
    return {pid: CardImage(key, alt) for pid, key, alt in await session.execute(stmt)}


async def _colors_by_product(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ColorRef]]:
    if not ids:
        return {}
    stmt = (
        select(Variant.product_id, Color.code, Color.name, Color.hex)
        .join(Color, Color.code == Variant.color_code)
        .where(Variant.product_id.in_(ids), Variant.active.is_(True))
        .distinct()
        .order_by(Variant.product_id, Color.name, Color.code)
    )
    result: dict[uuid.UUID, list[ColorRef]] = {}
    for pid, code, name, hex_ in await session.execute(stmt):
        result.setdefault(pid, []).append(ColorRef(code, name, hex_))
    return result


# ---------------------------------------------------------------------------- facetas


async def facets(session: AsyncSession, f: ProductFilter) -> Facets:
    """Cada dimensão é contada com os outros filtros aplicados, menos o dela."""
    v = aliased(Variant)

    size_join = [v.product_id == Product.id, _in_stock(v)]
    if f.colors:
        size_join.append(v.color_code.in_(f.colors))
    size_counts = (
        select(v.size_code.label("code"), func.count(distinct(Product.id)).label("n"))
        .join_from(Product, v, and_(*size_join))
        .where(*_conditions(f, skip="sizes"))
        .group_by(v.size_code)
        .subquery()
    )
    sizes = await session.execute(
        select(Size.code, Size.label, func.coalesce(size_counts.c.n, 0))
        .outerjoin(size_counts, size_counts.c.code == Size.code)
        .order_by(Size.position)
    )

    color_join = [v.product_id == Product.id, _in_stock(v)]
    if f.sizes:
        color_join.append(v.size_code.in_(f.sizes))
    color_counts = (
        select(v.color_code.label("code"), func.count(distinct(Product.id)).label("n"))
        .join_from(Product, v, and_(*color_join))
        .where(*_conditions(f, skip="colors"))
        .group_by(v.color_code)
        .subquery()
    )
    colors = await session.execute(
        select(Color.code, Color.name, Color.hex, func.coalesce(color_counts.c.n, 0))
        .outerjoin(color_counts, color_counts.c.code == Color.code)
        .order_by(Color.name, Color.code)
    )

    categories = await session.execute(
        select(Category.slug, Category.name, func.count(Product.id))
        .join_from(Product, Category, Category.id == Product.category_id)
        .where(*_conditions(f, skip="category"))
        .group_by(Category.id)
        .order_by(Category.position, Category.name)
    )

    low, high = (
        await session.execute(
            select(func.min(Product.min_price_cents), func.max(Product.min_price_cents)).where(
                *_conditions(f, skip="price")
            )
        )
    ).one()

    return Facets(
        sizes=[SizeFacet(code, label, int(n)) for code, label, n in sizes],
        colors=[ColorFacet(code, name, hex_, int(n)) for code, name, hex_, n in colors],
        categories=[CategoryFacet(slug, name, int(n)) for slug, name, n in categories],
        price=PriceRange(low, high),
    )


# ---------------------------------------------------------------------------- detalhe


async def product_detail(session: AsyncSession, slug: str) -> ProductDetail | None:
    product = (
        await session.execute(
            select(Product, Category.slug, Category.name)
            .join(Category, Category.id == Product.category_id)
            .where(Product.slug == slug, *_conditions(_NO_FILTER))
        )
    ).one_or_none()
    if product is None:
        return None
    p, category_slug, category_name = product
    variants = (
        await session.execute(
            select(Variant, Size.position)
            .join(Size, Size.code == Variant.size_code)
            .where(Variant.product_id == p.id, Variant.active.is_(True))
            .order_by(Variant.color_code, Size.position)
        )
    ).all()
    colors = (
        await session.execute(
            select(Color.code, Color.name, Color.hex)
            .where(Color.code.in_({row.Variant.color_code for row in variants}))
            .order_by(Color.name, Color.code)
        )
    ).all()
    sizes = (
        await session.execute(
            select(Size.code, Size.label)
            .where(Size.code.in_({row.Variant.size_code for row in variants}))
            .order_by(Size.position)
        )
    ).all()
    images = (
        await session.scalars(
            select(ProductImage)
            .where(ProductImage.product_id == p.id)
            .order_by(ProductImage.position, ProductImage.id)
        )
    ).all()
    return ProductDetail(
        slug=p.slug,
        name=p.name,
        description=p.description,
        attributes=p.attributes,
        category_slug=category_slug,
        category_name=category_name,
        min_price_cents=p.min_price_cents or 0,
        colors=[ColorRef(code, name, hex_) for code, name, hex_ in colors],
        sizes=[SizeRef(code, label) for code, label in sizes],
        variants=[
            PublicVariant(
                sku=row.Variant.sku,
                color_code=row.Variant.color_code,
                size_code=row.Variant.size_code,
                price_cents=effective_price(p.base_price_cents, row.Variant.price_cents),
                available=available(row.Variant.stock_on_hand, row.Variant.stock_reserved) > 0,
            )
            for row in variants
        ],
        images=[
            PublicImage(
                storage_key=i.storage_key,
                alt=i.alt,
                color_code=i.color_code,
                width=i.width,
                height=i.height,
                credit_author=i.credit_author,
                credit_source_url=i.credit_source_url,
                license=i.license,
            )
            for i in images
        ],
    )


_NO_FILTER = ProductFilter(
    category=None,
    collection=None,
    sizes=(),
    colors=(),
    price_min=None,
    price_max=None,
    q=None,
    sort="newest",
)


# ---------------------------------------------------------------------------- créditos


async def list_credits(session: AsyncSession) -> list[Credit]:
    """Imagens creditadas de produtos visíveis na vitrine, para a página /creditos."""
    stmt = (
        select(
            Product.name,
            ProductImage.storage_key,
            ProductImage.credit_author,
            ProductImage.credit_source_url,
            ProductImage.license,
        )
        .join(Product, Product.id == ProductImage.product_id)
        .where(
            *_conditions(_NO_FILTER),
            (ProductImage.credit_author.is_not(None))
            | (ProductImage.credit_source_url.is_not(None))
            | (ProductImage.license.is_not(None)),
        )
        .order_by(Product.name, Product.id, ProductImage.position, ProductImage.id)
    )
    return [Credit(*row) for row in await session.execute(stmt)]
