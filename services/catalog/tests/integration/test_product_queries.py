import base64
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from catalog.adapters.models import Category, Product, ProductImage, Variant
from catalog.adapters.product_queries import (
    ProductFilter,
    SortOrder,
    facets,
    list_products,
)
from catalog.application.cursor import encode_cursor
from ks_platform.errors import ProblemError

# (nome, preço base, [(cor, tamanho, estoque, ativa, preço próprio)])
type VariantSpec = tuple[str, str, int, bool, int | None]
CATALOG: list[tuple[str, int, list[VariantSpec]]] = [
    (
        "Moletom Zip Preto",
        25900,
        [("PRT", "P", 3, True, None), ("PRT", "M", 2, True, None), ("PRT", "G", 0, True, None)],
    ),
    ("Moletom Cinza", 19900, [("CNZ", "M", 5, True, None), ("CNZ", "G", 1, True, 17900)]),
    ("Camiseta Preta", 7900, [("PRT", "P", 0, True, None), ("PRT", "M", 0, True, None)]),
    (
        "Moletom Básico",
        15900,
        [("PRT", "M", 0, True, None), ("CNZ", "M", 4, True, None), ("PRT", "G", 2, True, None)],
    ),
    ("Calça Jogger", 18900, [("PRT", "G", 3, True, None), ("PRT", "M", 5, False, None)]),
    ("Bermuda Sarja", 12900, [("CNZ", "P", 1, True, None)]),
]
DRAFT: tuple[str, int, list[VariantSpec]] = (
    "Moletom Rascunho",
    9900,
    [("PRT", "M", 9, True, None)],
)


@dataclass(frozen=True)
class Seeded:
    category: str
    other_category: str


@pytest.fixture
async def session(migrated_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            yield s
    finally:
        await engine.dispose()


async def _add_product(
    s: AsyncSession,
    category_id: uuid.UUID,
    name: str,
    base: int,
    variants: list[VariantSpec],
    *,
    status: str = "active",
    published_at: datetime | None = None,
) -> uuid.UUID:
    product_id = uuid.uuid7()
    active_prices = [price or base for _, _, _, active, price in variants if active]
    await s.execute(
        insert(Product).values(
            id=product_id,
            slug=f"p-{product_id.hex[-12:]}",
            name=name,
            description="Peça de teste.",
            category_id=category_id,
            category_name_cache="Vestuário de teste",
            status=status,
            base_price_cents=base,
            min_price_cents=min(active_prices) if active_prices else None,
            published_at=published_at,
        )
    )
    for color, size, stock, active, price in variants:
        await s.execute(
            insert(Variant).values(
                id=uuid.uuid7(),
                product_id=product_id,
                sku=f"T-{uuid.uuid7().hex[-12:]}",
                color_code=color,
                size_code=size,
                price_cents=price,
                stock_on_hand=stock,
                active=active,
            )
        )
    await s.execute(
        insert(ProductImage).values(
            id=uuid.uuid7(),
            product_id=product_id,
            storage_key=f"products/{product_id.hex}.jpg",
            width=64,
            height=48,
            alt=f"Foto de {name}",
        )
    )
    return product_id


async def _add_category(s: AsyncSession, name: str) -> tuple[uuid.UUID, str]:
    category_id = uuid.uuid7()
    slug = f"cat-{category_id.hex[-12:]}"
    await s.execute(insert(Category).values(id=category_id, slug=slug, name=name))
    return category_id, slug


@pytest.fixture
async def seeded(session: AsyncSession) -> Seeded:
    category_id, slug = await _add_category(session, "Vestuário de teste")
    other_id, other_slug = await _add_category(session, "Outra categoria")
    start = datetime.now(UTC)
    for i, (name, base, variants) in enumerate(CATALOG):
        published = start - timedelta(minutes=i)
        await _add_product(session, category_id, name, base, variants, published_at=published)
    name, base, variants = DRAFT
    await _add_product(session, category_id, name, base, variants, status="draft")
    await _add_product(
        session, other_id, "Moletom Outro", 9900, [("CNZ", "M", 1, True, None)], published_at=start
    )
    await session.commit()
    return Seeded(category=slug, other_category=other_slug)


def _filter(seeded: Seeded, **overrides: object) -> ProductFilter:
    base = ProductFilter(
        category=seeded.category,
        collection=None,
        sizes=(),
        colors=(),
        price_min=None,
        price_max=None,
        q=None,
        sort="newest",
    )
    return replace(base, **overrides)  # pyright: ignore[reportArgumentType]


async def _names(session: AsyncSession, f: ProductFilter) -> list[str]:
    page = await list_products(session, f, None, 100)
    return [card.name for card in page.items]


async def test_lists_only_active(session: AsyncSession, seeded: Seeded) -> None:
    page = await list_products(session, _filter(seeded), None, 100)
    names = [card.name for card in page.items]
    assert names == [name for name, _, _ in CATALOG]
    assert page.next_cursor is None
    cards = {card.name: card for card in page.items}
    assert cards["Camiseta Preta"].sold_out is True
    assert cards["Moletom Zip Preto"].sold_out is False
    assert cards["Moletom Cinza"].min_price_cents == 17900
    assert [c.code for c in cards["Moletom Básico"].colors] == ["CNZ", "PRT"]
    assert [c.code for c in cards["Calça Jogger"].colors] == ["PRT"]
    image = cards["Bermuda Sarja"].image
    assert image is not None
    assert image.alt == "Foto de Bermuda Sarja"


async def test_product_without_active_variants_excluded(session: AsyncSession) -> None:
    category_id, slug = await _add_category(session, "Sem variantes")
    await _add_product(
        session,
        category_id,
        "Gorro Inativo",
        5900,
        [("PRT", "M", 4, False, None)],
        published_at=datetime.now(UTC),
    )
    await session.commit()
    f = ProductFilter(
        category=slug,
        collection=None,
        sizes=(),
        colors=(),
        price_min=None,
        price_max=None,
        q=None,
        sort="newest",
    )
    assert await _names(session, f) == []


@pytest.mark.parametrize("q", ["moletom basico", "moletom básico", "MOLETOM BÁSICO"])
async def test_search_accent_insensitive(session: AsyncSession, seeded: Seeded, q: str) -> None:
    assert await _names(session, _filter(seeded, q=q, sort="relevance")) == ["Moletom Básico"]


async def test_search_multiword_and(session: AsyncSession, seeded: Seeded) -> None:
    names = await _names(session, _filter(seeded, q="moletom preto", sort="relevance"))
    assert names == ["Moletom Zip Preto"]


async def test_search_name_outranks_category(session: AsyncSession, seeded: Seeded) -> None:
    # "vestuário" só aparece na categoria (peso B); "moletom" no nome (peso A).
    names = await _names(session, _filter(seeded, q="moletom", sort="relevance"))
    assert set(names) == {"Moletom Zip Preto", "Moletom Cinza", "Moletom Básico"}
    everything = await _names(session, _filter(seeded, q="vestuario", sort="relevance"))
    assert set(everything) == {name for name, _, _ in CATALOG}


async def test_relevance_without_q_falls_back_to_newest(
    session: AsyncSession, seeded: Seeded
) -> None:
    f = _filter(seeded, sort="relevance")
    assert f.sort == "newest"
    assert await _names(session, f) == [name for name, _, _ in CATALOG]


async def test_size_and_color_filters_combine(session: AsyncSession, seeded: Seeded) -> None:
    names = await _names(session, _filter(seeded, sizes=("M",), colors=("CNZ",)))
    assert names == ["Moletom Cinza", "Moletom Básico"]
    names = await _names(session, _filter(seeded, sizes=("M", "G"), colors=("PRT",)))
    assert names == ["Moletom Zip Preto", "Moletom Básico", "Calça Jogger"]


async def test_sold_out_variant_not_matched_by_size_filter(
    session: AsyncSession, seeded: Seeded
) -> None:
    # Zip Preto tem G sem estoque; Calça tem M inativa com estoque.
    assert await _names(session, _filter(seeded, sizes=("G",))) == [
        "Moletom Cinza",
        "Moletom Básico",
        "Calça Jogger",
    ]
    assert await _names(session, _filter(seeded, sizes=("M",), colors=("PRT",))) == [
        "Moletom Zip Preto"
    ]


async def test_unknown_size_or_color_matches_nothing(session: AsyncSession, seeded: Seeded) -> None:
    assert await _names(session, _filter(seeded, sizes=("ZZ",))) == []
    assert await _names(session, _filter(seeded, colors=("NOPE",))) == []


async def test_facets_exclude_own_dimension(session: AsyncSession, seeded: Seeded) -> None:
    result = await facets(session, _filter(seeded, sizes=("M",)))
    sizes = {s.code: s.count for s in result.sizes}
    assert [s.code for s in result.sizes] == ["PP", "P", "M", "G", "GG", "XG", "XGG"]
    assert sizes == {"PP": 0, "P": 2, "M": 3, "G": 3, "GG": 0, "XG": 0, "XGG": 0}
    colors = {c.code: c.count for c in result.colors}
    assert colors["PRT"] == 1
    assert colors["CNZ"] == 2
    assert colors["BRC"] == 0
    categories = {c.slug: c.count for c in result.categories}
    assert categories[seeded.category] == 3
    assert categories[seeded.other_category] == 1
    assert (result.price.min, result.price.max) == (15900, 25900)


async def test_facets_price_ignores_price_filter(session: AsyncSession, seeded: Seeded) -> None:
    result = await facets(session, _filter(seeded, price_min=20000))
    assert (result.price.min, result.price.max) == (7900, 25900)
    empty = await facets(session, _filter(seeded, q="inexistentexyz", sort="relevance"))
    assert (empty.price.min, empty.price.max) == (None, None)


@pytest.mark.parametrize(
    ("sort", "q"),
    [("newest", None), ("price_asc", None), ("price_desc", None), ("relevance", "vestuario")],
)
async def test_keyset_pagination_stable(
    session: AsyncSession, seeded: Seeded, sort: SortOrder, q: str | None
) -> None:
    f = _filter(seeded, sort=sort, q=q)
    full = [card.slug for card in (await list_products(session, f, None, 100)).items]
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        page = await list_products(session, f, cursor, 2)
        assert len(page.items) <= 2
        seen.extend(card.slug for card in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == full
    assert len(set(seen)) == len(seen) == len(CATALOG)


async def test_price_sort_and_range(session: AsyncSession, seeded: Seeded) -> None:
    ranged = _filter(seeded, price_min=15000, price_max=19000, sort="price_asc")
    assert await _names(session, ranged) == ["Moletom Básico", "Moletom Cinza", "Calça Jogger"]
    descending = replace(ranged, sort="price_desc")
    assert await _names(session, descending) == [
        "Calça Jogger",
        "Moletom Cinza",
        "Moletom Básico",
    ]
    exact = _filter(seeded, price_min=7900, price_max=7900)
    assert await _names(session, exact) == ["Camiseta Preta"]


def test_filter_rules() -> None:
    blank = ProductFilter(
        category=None,
        collection=None,
        sizes=(),
        colors=(),
        price_min=None,
        price_max=None,
        q="   ",
        sort="relevance",
    )
    assert blank.q is None
    assert blank.sort == "newest"
    assert replace(blank, q=" moletom ").q == "moletom"
    with pytest.raises(ProblemError) as too_long:
        replace(blank, q="x" * 201)
    assert (too_long.value.status, too_long.value.code) == (422, "catalog.search.query_too_long")
    assert replace(blank, q="x" * 200).q == "x" * 200
    with pytest.raises(ProblemError) as inverted:
        replace(blank, price_min=200, price_max=100)
    assert inverted.value.status == 422


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.mark.parametrize(
    "cursor",
    [
        "lixo",
        _b64(b'{"s":"newest","k":'),
        _b64(b"[" * 10_000),
        "a" * 513,
        encode_cursor({"s": "price_asc", "k": "100", "id": str(uuid.uuid7())}),
        encode_cursor({"s": "newest", "k": "ontem", "id": str(uuid.uuid7())}),
        encode_cursor({"s": "newest", "k": "2026-10-24T10:00:00", "id": str(uuid.uuid7())}),
        encode_cursor({"s": "newest", "k": "2026-10-24T10:00:00+00:00", "id": "x"}),
        encode_cursor({"s": "newest", "id": str(uuid.uuid7())}),
    ],
    ids=[
        "lixo",
        "truncated-json",
        "nested-10k",
        "513-chars",
        "other-sort",
        "bad-timestamp",
        "naive-timestamp",
        "bad-id",
        "missing-key",
    ],
)
async def test_bad_cursor_422(session: AsyncSession, seeded: Seeded, cursor: str) -> None:
    with pytest.raises(ProblemError) as raised:
        await list_products(session, _filter(seeded), cursor, 24)
    assert (raised.value.status, raised.value.code) == (422, "catalog.pagination.invalid_cursor")


@pytest.mark.parametrize("k", ["-1", "1e3", "99999999999999999999", "abc"])
async def test_bad_price_cursor_value_422(session: AsyncSession, seeded: Seeded, k: str) -> None:
    cursor = encode_cursor({"s": "price_asc", "k": k, "id": str(uuid.uuid7())})
    with pytest.raises(ProblemError) as raised:
        await list_products(session, _filter(seeded, sort="price_asc"), cursor, 24)
    assert raised.value.code == "catalog.pagination.invalid_cursor"


@pytest.mark.parametrize("k", ["nan", "inf", "-inf", "abc"])
async def test_bad_relevance_cursor_value_422(
    session: AsyncSession, seeded: Seeded, k: str
) -> None:
    cursor = encode_cursor({"s": "relevance", "k": k, "id": str(uuid.uuid7())})
    with pytest.raises(ProblemError) as raised:
        await list_products(session, _filter(seeded, sort="relevance", q="moletom"), cursor, 24)
    assert raised.value.code == "catalog.pagination.invalid_cursor"
