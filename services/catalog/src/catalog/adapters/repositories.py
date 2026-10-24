import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import (
    ColumnElement,
    and_,
    case,
    delete,
    exists,
    func,
    or_,
    select,
    tuple_,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.adapters.models import (
    Category,
    Collection,
    CollectionProduct,
    Color,
    Product,
    ProductImage,
    Size,
    StockMovement,
    StorefrontSettings,
    Variant,
)
from catalog.application.ports import (
    CatalogUnitOfWork,
    CategoryRecord,
    CollectionRecord,
    ImageRecord,
    MovementCursor,
    MovementRecord,
    Overview,
    ProductCursor,
    ProductFilter,
    ProductRecord,
    ProductRow,
    RecentMovement,
    UnitOfWorkFactory,
    VariantRecord,
)
from catalog.domain.variants import NewVariant

# Updates em lote não sincronizam a identity map; leituras usam populate_existing.
_NO_SYNC = {"synchronize_session": False}
_FRESH = {"populate_existing": True}


def _category(c: Category) -> CategoryRecord:
    return CategoryRecord(c.id, c.slug, c.name, c.parent_id, c.position)


def _variant(v: Variant) -> VariantRecord:
    return VariantRecord(
        id=v.id,
        product_id=v.product_id,
        sku=v.sku,
        color_code=v.color_code,
        size_code=v.size_code,
        price_cents=v.price_cents,
        stock_on_hand=v.stock_on_hand,
        stock_reserved=v.stock_reserved,
        version=v.version,
        active=v.active,
    )


def _image(i: ProductImage) -> ImageRecord:
    return ImageRecord(
        id=i.id,
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


def _movement(m: StockMovement) -> MovementRecord:
    return MovementRecord(m.id, m.variant_id, m.delta, m.reason, m.note, m.actor_id, m.created_at)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SqlTaxonomyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_categories(self) -> list[CategoryRecord]:
        rows = await self._s.scalars(select(Category).order_by(Category.position, Category.name))
        return [_category(c) for c in rows]

    async def get_category(self, category_id: uuid.UUID) -> CategoryRecord | None:
        stmt = select(Category).where(Category.id == category_id).execution_options(**_FRESH)
        category = await self._s.scalar(stmt)
        return None if category is None else _category(category)

    async def category_slug_exists(self, slug: str, *, exclude: uuid.UUID | None = None) -> bool:
        cond = Category.slug == slug
        if exclude is not None:
            cond = and_(cond, Category.id != exclude)
        return bool(await self._s.scalar(select(exists().where(cond))))

    async def add_category(
        self, slug: str, name: str, parent_id: uuid.UUID | None, position: int
    ) -> CategoryRecord:
        category = Category(slug=slug, name=name, parent_id=parent_id, position=position)
        self._s.add(category)
        await self._s.flush()
        return _category(category)

    async def update_category(self, category_id: uuid.UUID, fields: dict[str, Any]) -> None:
        stmt = update(Category).where(Category.id == category_id).values(**fields)
        await self._s.execute(stmt.execution_options(**_NO_SYNC))

    async def category_in_use(self, category_id: uuid.UUID) -> bool:
        products = exists().where(Product.category_id == category_id)
        children = exists().where(Category.parent_id == category_id)
        return bool(await self._s.scalar(select(or_(products, children))))

    async def delete_category(self, category_id: uuid.UUID) -> None:
        stmt = delete(Category).where(Category.id == category_id)
        await self._s.execute(stmt.execution_options(**_NO_SYNC))

    async def _collection_records(
        self, collections: Sequence[Collection]
    ) -> list[CollectionRecord]:
        ids = [c.id for c in collections]
        links = await self._s.execute(
            select(CollectionProduct.collection_id, CollectionProduct.product_id)
            .where(CollectionProduct.collection_id.in_(ids))
            .order_by(CollectionProduct.position)
        )
        by_collection: dict[uuid.UUID, list[uuid.UUID]] = {cid: [] for cid in ids}
        for collection_id, product_id in links:
            by_collection[collection_id].append(product_id)
        return [
            CollectionRecord(
                id=c.id,
                slug=c.slug,
                name=c.name,
                description=c.description,
                featured=c.featured,
                position=c.position,
                product_ids=by_collection[c.id],
            )
            for c in collections
        ]

    async def list_collections(self) -> list[CollectionRecord]:
        rows = await self._s.scalars(
            select(Collection).order_by(Collection.position, Collection.name)
        )
        return await self._collection_records(list(rows))

    async def get_collection(self, collection_id: uuid.UUID) -> CollectionRecord | None:
        stmt = select(Collection).where(Collection.id == collection_id).execution_options(**_FRESH)
        collection = await self._s.scalar(stmt)
        if collection is None:
            return None
        return (await self._collection_records([collection]))[0]

    async def collection_slug_exists(self, slug: str, *, exclude: uuid.UUID | None = None) -> bool:
        cond = Collection.slug == slug
        if exclude is not None:
            cond = and_(cond, Collection.id != exclude)
        return bool(await self._s.scalar(select(exists().where(cond))))

    async def add_collection(
        self, slug: str, name: str, description: str | None, featured: bool, position: int
    ) -> CollectionRecord:
        collection = Collection(
            slug=slug, name=name, description=description, featured=featured, position=position
        )
        self._s.add(collection)
        await self._s.flush()
        return (await self._collection_records([collection]))[0]

    async def update_collection(self, collection_id: uuid.UUID, fields: dict[str, Any]) -> None:
        stmt = update(Collection).where(Collection.id == collection_id).values(**fields)
        await self._s.execute(stmt.execution_options(**_NO_SYNC))

    async def delete_collection(self, collection_id: uuid.UUID) -> bool:
        stmt = delete(Collection).where(Collection.id == collection_id).returning(Collection.id)
        deleted = await self._s.scalar(stmt.execution_options(**_NO_SYNC))
        return deleted is not None

    async def set_collection_products(
        self, collection_id: uuid.UUID, product_ids: list[uuid.UUID]
    ) -> None:
        await self._s.execute(
            delete(CollectionProduct).where(CollectionProduct.collection_id == collection_id)
        )
        if product_ids:
            await self._s.execute(
                insert(CollectionProduct).values(
                    [
                        {"collection_id": collection_id, "product_id": pid, "position": index}
                        for index, pid in enumerate(product_ids)
                    ]
                )
            )


class SqlProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, product_id: uuid.UUID, *, for_update: bool = False) -> ProductRecord | None:
        stmt = (
            select(Product, Category)
            .join(Category, Category.id == Product.category_id)
            .where(Product.id == product_id)
            .execution_options(**_FRESH)
        )
        if for_update:
            stmt = stmt.with_for_update(of=Product)
        row = (await self._s.execute(stmt)).one_or_none()
        if row is None:
            return None
        product, category = row
        variants = await self._s.scalars(
            select(Variant)
            .join(Size, Size.code == Variant.size_code)
            .where(Variant.product_id == product_id)
            .order_by(Variant.color_code, Size.position)
            .execution_options(**_FRESH)
        )
        images = await self._s.scalars(
            select(ProductImage)
            .where(ProductImage.product_id == product_id)
            .order_by(ProductImage.position, ProductImage.created_at)
            .execution_options(**_FRESH)
        )
        return ProductRecord(
            id=product.id,
            slug=product.slug,
            name=product.name,
            description=product.description,
            category=_category(category),
            status=product.status,
            base_price_cents=product.base_price_cents,
            min_price_cents=product.min_price_cents,
            attributes=product.attributes,
            version=product.version,
            published_at=product.published_at,
            created_at=product.created_at,
            updated_at=product.updated_at,
            variants=[_variant(v) for v in variants],
            images=[_image(i) for i in images],
        )

    async def slug_exists(self, slug: str, *, exclude: uuid.UUID | None = None) -> bool:
        cond = Product.slug == slug
        if exclude is not None:
            cond = and_(cond, Product.id != exclude)
        return bool(await self._s.scalar(select(exists().where(cond))))

    async def existing_ids(self, product_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not product_ids:
            return set()
        rows = await self._s.scalars(select(Product.id).where(Product.id.in_(product_ids)))
        return set(rows)

    async def add(
        self,
        *,
        slug: str,
        name: str,
        description: str | None,
        category: CategoryRecord,
        base_price_cents: int,
        attributes: dict[str, Any],
    ) -> uuid.UUID:
        product = Product(
            slug=slug,
            name=name,
            description=description,
            category_id=category.id,
            category_name_cache=category.name,
            base_price_cents=base_price_cents,
            attributes=attributes,
        )
        self._s.add(product)
        await self._s.flush()
        return product.id

    async def update_versioned(
        self, product_id: uuid.UUID, expected_version: int, fields: dict[str, Any]
    ) -> bool:
        stmt = (
            update(Product)
            .where(Product.id == product_id, Product.version == expected_version)
            .values(**fields, version=Product.version + 1)
            .returning(Product.id)
        )
        return await self._s.scalar(stmt.execution_options(**_NO_SYNC)) is not None

    async def set_status(self, product_id: uuid.UUID, status: str) -> None:
        values: dict[str, Any] = {"status": status, "version": Product.version + 1}
        if status == "active":
            values["published_at"] = func.coalesce(Product.published_at, func.now())
        stmt = update(Product).where(Product.id == product_id).values(**values)
        await self._s.execute(stmt.execution_options(**_NO_SYNC))

    async def refresh_category_cache(self, category_id: uuid.UUID, name: str) -> None:
        stmt = (
            update(Product)
            .where(Product.category_id == category_id)
            .values(category_name_cache=name)
        )
        await self._s.execute(stmt.execution_options(**_NO_SYNC))

    async def recompute_min_price(self, product_id: uuid.UUID) -> None:
        # Menor preço efetivo entre as variantes ativas; sem variante ativa, fica nulo.
        min_price = (
            select(func.min(func.coalesce(Variant.price_cents, Product.base_price_cents)))
            .where(Variant.product_id == Product.id, Variant.active.is_(True))
            .scalar_subquery()
        )
        stmt = update(Product).where(Product.id == product_id).values(min_price_cents=min_price)
        await self._s.execute(stmt.execution_options(**_NO_SYNC))

    async def list(
        self, filters: ProductFilter, cursor: ProductCursor | None, limit: int
    ) -> list[ProductRow]:
        available = func.greatest(Variant.stock_on_hand - Variant.stock_reserved, 0)
        totals = (
            select(
                Variant.product_id.label("product_id"),
                func.count().label("variant_count"),
                func.sum(case((Variant.active, available), else_=0)).label("total_available"),
            )
            .group_by(Variant.product_id)
            .subquery()
        )
        stmt = (
            select(
                Product.id,
                Product.slug,
                Product.name,
                Product.status,
                Product.min_price_cents,
                Product.updated_at,
                Category,
                func.coalesce(totals.c.variant_count, 0),
                func.coalesce(totals.c.total_available, 0),
            )
            .join(Category, Category.id == Product.category_id)
            .outerjoin(totals, totals.c.product_id == Product.id)
        )
        conditions: list[ColumnElement[bool]] = []
        q = (filters.q or "").strip()
        if q:
            pattern = f"%{_escape_like(q)}%"
            conditions.append(
                or_(
                    Product.name.ilike(pattern, escape="\\"),
                    Product.slug.ilike(pattern, escape="\\"),
                )
            )
        if filters.status:
            conditions.append(Product.status == filters.status)
        if filters.category_slug:
            conditions.append(Category.slug == filters.category_slug)
        if filters.slug:
            conditions.append(Product.slug == filters.slug)
        if cursor is not None:
            conditions.append(
                tuple_(Product.updated_at, Product.id) < tuple_(cursor.updated_at, cursor.id)
            )
        stmt = (
            stmt.where(*conditions)
            .order_by(Product.updated_at.desc(), Product.id.desc())
            .limit(limit)
        )
        rows = await self._s.execute(stmt)
        return [
            ProductRow(
                id=pid,
                slug=slug,
                name=name,
                status=status,
                category=_category(category),
                min_price_cents=min_price,
                variant_count=int(count),
                total_available=int(total),
                updated_at=updated_at,
            )
            for pid, slug, name, status, min_price, updated_at, category, count, total in rows
        ]

    async def known_colors(self, codes: list[str]) -> set[str]:
        return set(await self._s.scalars(select(Color.code).where(Color.code.in_(codes))))

    async def known_sizes(self, codes: list[str]) -> set[str]:
        return set(await self._s.scalars(select(Size.code).where(Size.code.in_(codes))))

    async def add_variants(self, product_id: uuid.UUID, variants: list[NewVariant]) -> None:
        await self._s.execute(
            insert(Variant).values(
                [
                    {
                        "id": uuid.uuid7(),
                        "product_id": product_id,
                        "sku": v.sku,
                        "color_code": v.color_code,
                        "size_code": v.size_code,
                    }
                    for v in variants
                ]
            )
        )

    async def get_variant(
        self, variant_id: uuid.UUID, *, for_update: bool = False
    ) -> VariantRecord | None:
        stmt = select(Variant).where(Variant.id == variant_id).execution_options(**_FRESH)
        if for_update:
            stmt = stmt.with_for_update()
        variant = await self._s.scalar(stmt)
        return None if variant is None else _variant(variant)

    async def update_variant_versioned(
        self, variant_id: uuid.UUID, expected_version: int, fields: dict[str, Any]
    ) -> bool:
        stmt = (
            update(Variant)
            .where(Variant.id == variant_id, Variant.version == expected_version)
            .values(**fields, version=Variant.version + 1)
            .returning(Variant.id)
        )
        return await self._s.scalar(stmt.execution_options(**_NO_SYNC)) is not None


class SqlStockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def apply(
        self,
        variant_id: uuid.UUID,
        new_on_hand: int,
        delta: int,
        reason: str,
        note: str | None,
        actor_id: uuid.UUID,
    ) -> MovementRecord:
        movement = StockMovement(
            variant_id=variant_id, delta=delta, reason=reason, note=note, actor_id=actor_id
        )
        self._s.add(movement)
        await self._s.flush()
        await self._s.refresh(movement, ["created_at"])
        stmt = update(Variant).where(Variant.id == variant_id).values(stock_on_hand=new_on_hand)
        await self._s.execute(stmt.execution_options(**_NO_SYNC))
        return _movement(movement)

    async def list_movements(
        self, variant_id: uuid.UUID, cursor: MovementCursor | None, limit: int
    ) -> list[MovementRecord]:
        stmt = select(StockMovement).where(StockMovement.variant_id == variant_id)
        if cursor is not None:
            stmt = stmt.where(
                tuple_(StockMovement.created_at, StockMovement.id)
                < tuple_(cursor.created_at, cursor.id)
            )
        stmt = stmt.order_by(StockMovement.created_at.desc(), StockMovement.id.desc()).limit(limit)
        return [_movement(m) for m in await self._s.scalars(stmt)]

    async def overview(self, recent_limit: int) -> Overview:
        counts = {"draft": 0, "active": 0, "archived": 0}
        for status, count in await self._s.execute(
            select(Product.status, func.count()).group_by(Product.status)
        ):
            counts[status] = int(count)
        out_of_stock = await self._s.scalar(
            select(func.count())
            .select_from(Variant)
            .join(Product, Product.id == Variant.product_id)
            .where(
                Variant.active.is_(True),
                Product.status != "archived",
                Variant.stock_on_hand - Variant.stock_reserved <= 0,
            )
        )
        recent = await self._s.execute(
            select(StockMovement, Variant.sku, Variant.product_id, Product.name)
            .join(Variant, Variant.id == StockMovement.variant_id)
            .join(Product, Product.id == Variant.product_id)
            .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
            .limit(recent_limit)
        )
        return Overview(
            products_by_status=counts,
            out_of_stock_variants=int(out_of_stock or 0),
            recent_movements=[
                RecentMovement(_movement(m), sku, product_id, name)
                for m, sku, product_id, name in recent
            ],
        )


class SqlSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self) -> dict[str, Any] | None:
        return await self._s.scalar(
            select(StorefrontSettings.data).where(StorefrontSettings.id == 1)
        )

    async def put(self, data: dict[str, Any]) -> None:
        stmt = insert(StorefrontSettings).values(id=1, data=data)
        stmt = stmt.on_conflict_do_update(
            index_elements=[StorefrontSettings.id],
            set_={"data": stmt.excluded.data, "updated_at": func.now()},
        )
        await self._s.execute(stmt)


class SqlCatalogUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._taxonomy = SqlTaxonomyRepository(session)
        self._products = SqlProductRepository(session)
        self._stock = SqlStockRepository(session)
        self._settings = SqlSettingsRepository(session)

    @property
    def taxonomy(self) -> SqlTaxonomyRepository:
        return self._taxonomy

    @property
    def products(self) -> SqlProductRepository:
        return self._products

    @property
    def stock(self) -> SqlStockRepository:
        return self._stock

    @property
    def settings(self) -> SqlSettingsRepository:
        return self._settings


def sql_unit_of_work(session_factory: async_sessionmaker[AsyncSession]) -> UnitOfWorkFactory:
    """Cada chamada abre uma sessão e uma transação próprias (commit ao sair sem erro)."""

    @asynccontextmanager
    async def open_uow() -> AsyncIterator[CatalogUnitOfWork]:
        async with session_factory() as session, session.begin():
            yield SqlCatalogUnitOfWork(session)

    return open_uow
