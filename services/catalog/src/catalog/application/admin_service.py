"""Casos de uso do admin do catálogo. Cada método roda numa transação própria."""

import uuid
from datetime import datetime
from typing import Any

from catalog.application.cursor import decode_cursor, encode_cursor, invalid_cursor
from catalog.application.ports import (
    CategoryRecord,
    CollectionRecord,
    ImageRecord,
    ImageStorage,
    MovementCursor,
    MovementRecord,
    Overview,
    ProductCursor,
    ProductFilter,
    ProductRecord,
    ProductRepository,
    ProductRow,
    TaxonomyRepository,
    UnitOfWorkFactory,
    VariantRecord,
)
from catalog.domain.images import storage_key
from catalog.domain.publishing import PublishCheck, publish_blockers
from catalog.domain.slugs import slugify
from catalog.domain.stock import StockError, apply_adjustment, effective_price
from catalog.domain.variants import generate_variant_grid

CATEGORY_NOT_FOUND = "catalog.category.not_found"
CATEGORY_SLUG_TAKEN = "catalog.category.slug_taken"
CATEGORY_IN_USE = "catalog.category.in_use"
CATEGORY_INVALID_SLUG = "catalog.category.invalid_slug"
COLLECTION_NOT_FOUND = "catalog.collection.not_found"
COLLECTION_SLUG_TAKEN = "catalog.collection.slug_taken"
COLLECTION_INVALID_SLUG = "catalog.collection.invalid_slug"
COLLECTION_DUPLICATE_PRODUCT = "catalog.collection.duplicate_product"
PRODUCT_NOT_FOUND = "catalog.product.not_found"
PRODUCT_SLUG_TAKEN = "catalog.product.slug_taken"
PRODUCT_INVALID_SLUG = "catalog.product.invalid_slug"
PRODUCT_VERSION_CONFLICT = "catalog.product.version_conflict"
PRODUCT_NOT_PUBLISHABLE = "catalog.product.not_publishable"
VARIANT_NOT_FOUND = "catalog.variant.not_found"
VARIANT_VERSION_CONFLICT = "catalog.variant.version_conflict"
VARIANT_UNKNOWN_OPTION = "catalog.variant.unknown_option"
CATEGORY_PARENT_CYCLE = "catalog.category.parent_cycle"
SETTINGS_NOT_FOUND = "catalog.storefront.settings_not_found"
IMAGE_NOT_FOUND = "catalog.image.not_found"
IMAGE_UNKNOWN_COLOR = "catalog.image.unknown_color"

RECENT_MOVEMENTS = 10


class CatalogError(Exception):
    def __init__(self, code: str, errors: dict[str, list[str]] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.errors = errors


def _slug_or_error(name: str, code: str) -> str:
    try:
        return slugify(name)
    except ValueError as exc:
        raise CatalogError(code) from exc


# ---------------------------------------------------------------------------- cursores


def _parse_position(payload: dict[str, str], keys: tuple[str, str]) -> tuple[datetime, uuid.UUID]:
    try:
        moment = datetime.fromisoformat(payload[keys[0]])
        row_id = uuid.UUID(payload[keys[1]])
    except ValueError as exc:
        raise invalid_cursor() from exc
    if moment.tzinfo is None:
        raise invalid_cursor()
    return moment, row_id


def encode_product_cursor(row: ProductRow) -> str:
    return encode_cursor({"u": row.updated_at.isoformat(), "i": str(row.id)})


def decode_product_cursor(token: str) -> ProductCursor:
    keys = ("u", "i")
    updated_at, row_id = _parse_position(decode_cursor(token, keys), keys)
    return ProductCursor(updated_at, row_id)


def encode_movement_cursor(movement: MovementRecord) -> str:
    return encode_cursor({"c": movement.created_at.isoformat(), "i": str(movement.id)})


def decode_movement_cursor(token: str) -> MovementCursor:
    keys = ("c", "i")
    created_at, row_id = _parse_position(decode_cursor(token, keys), keys)
    return MovementCursor(created_at, row_id)


class AdminCatalogService:
    def __init__(self, uow: UnitOfWorkFactory, storage: ImageStorage) -> None:
        self._uow = uow
        self._storage = storage

    # ------------------------------------------------------------------------ categorias

    async def list_categories(self) -> list[CategoryRecord]:
        async with self._uow() as uow:
            return await uow.taxonomy.list_categories()

    async def create_category(
        self, name: str, slug: str | None, parent_id: uuid.UUID | None, position: int
    ) -> CategoryRecord:
        slug = slug or _slug_or_error(name, CATEGORY_INVALID_SLUG)
        async with self._uow() as uow:
            if parent_id is not None and await uow.taxonomy.get_category(parent_id) is None:
                raise CatalogError(CATEGORY_NOT_FOUND)
            if await uow.taxonomy.category_slug_exists(slug):
                raise CatalogError(CATEGORY_SLUG_TAKEN)
            return await uow.taxonomy.add_category(slug, name, parent_id, position)

    async def update_category(
        self, category_id: uuid.UUID, fields: dict[str, Any]
    ) -> CategoryRecord:
        async with self._uow() as uow:
            if await uow.taxonomy.get_category(category_id) is None:
                raise CatalogError(CATEGORY_NOT_FOUND)
            slug = fields.get("slug")
            if slug and await uow.taxonomy.category_slug_exists(slug, exclude=category_id):
                raise CatalogError(CATEGORY_SLUG_TAKEN)
            parent_id = fields.get("parent_id")
            if parent_id is not None:
                await self._check_parent(uow.taxonomy, category_id, parent_id)
            await uow.taxonomy.update_category(category_id, fields)
            if "name" in fields:
                await uow.products.refresh_category_cache(category_id, fields["name"])
            category = await uow.taxonomy.get_category(category_id)
            assert category is not None  # noqa: S101
            return category

    @staticmethod
    async def _check_parent(
        taxonomy: TaxonomyRepository, category_id: uuid.UUID, parent_id: uuid.UUID
    ) -> None:
        """O novo pai deve existir e não pode ser a própria categoria nem um descendente dela."""
        if await taxonomy.get_category(parent_id) is None:
            raise CatalogError(CATEGORY_NOT_FOUND)
        seen: set[uuid.UUID] = set()
        current: uuid.UUID | None = parent_id
        while current is not None and current not in seen:
            if current == category_id:
                raise CatalogError(CATEGORY_PARENT_CYCLE)
            seen.add(current)
            ancestor = await taxonomy.get_category(current)
            current = None if ancestor is None else ancestor.parent_id

    async def delete_category(self, category_id: uuid.UUID) -> None:
        async with self._uow() as uow:
            if await uow.taxonomy.get_category(category_id) is None:
                raise CatalogError(CATEGORY_NOT_FOUND)
            if await uow.taxonomy.category_in_use(category_id):
                raise CatalogError(CATEGORY_IN_USE)
            await uow.taxonomy.delete_category(category_id)

    # ------------------------------------------------------------------------ coleções

    async def list_collections(self) -> list[CollectionRecord]:
        async with self._uow() as uow:
            return await uow.taxonomy.list_collections()

    async def create_collection(
        self,
        name: str,
        slug: str | None,
        description: str | None,
        featured: bool,
        position: int,
    ) -> CollectionRecord:
        slug = slug or _slug_or_error(name, COLLECTION_INVALID_SLUG)
        async with self._uow() as uow:
            if await uow.taxonomy.collection_slug_exists(slug):
                raise CatalogError(COLLECTION_SLUG_TAKEN)
            return await uow.taxonomy.add_collection(slug, name, description, featured, position)

    async def update_collection(
        self, collection_id: uuid.UUID, fields: dict[str, Any]
    ) -> CollectionRecord:
        async with self._uow() as uow:
            if await uow.taxonomy.get_collection(collection_id) is None:
                raise CatalogError(COLLECTION_NOT_FOUND)
            slug = fields.get("slug")
            if slug and await uow.taxonomy.collection_slug_exists(slug, exclude=collection_id):
                raise CatalogError(COLLECTION_SLUG_TAKEN)
            await uow.taxonomy.update_collection(collection_id, fields)
            collection = await uow.taxonomy.get_collection(collection_id)
            assert collection is not None  # noqa: S101
            return collection

    async def delete_collection(self, collection_id: uuid.UUID) -> None:
        async with self._uow() as uow:
            if not await uow.taxonomy.delete_collection(collection_id):
                raise CatalogError(COLLECTION_NOT_FOUND)

    async def set_collection_products(
        self, collection_id: uuid.UUID, product_ids: list[uuid.UUID]
    ) -> CollectionRecord:
        if len(set(product_ids)) != len(product_ids):
            raise CatalogError(COLLECTION_DUPLICATE_PRODUCT)
        async with self._uow() as uow:
            if await uow.taxonomy.get_collection(collection_id) is None:
                raise CatalogError(COLLECTION_NOT_FOUND)
            if await uow.products.existing_ids(product_ids) != set(product_ids):
                raise CatalogError(PRODUCT_NOT_FOUND)
            await uow.taxonomy.set_collection_products(collection_id, product_ids)
            collection = await uow.taxonomy.get_collection(collection_id)
            assert collection is not None  # noqa: S101
            return collection

    # ------------------------------------------------------------------------ produtos

    async def list_products(
        self, filters: ProductFilter, cursor: str | None, limit: int
    ) -> tuple[list[ProductRow], str | None]:
        position = decode_product_cursor(cursor) if cursor else None
        async with self._uow() as uow:
            rows = await uow.products.list(filters, position, limit + 1)
        if len(rows) > limit:
            rows = rows[:limit]
            return rows, encode_product_cursor(rows[-1])
        return rows, None

    async def get_product(self, product_id: uuid.UUID) -> ProductRecord:
        async with self._uow() as uow:
            product = await uow.products.get(product_id)
        if product is None:
            raise CatalogError(PRODUCT_NOT_FOUND)
        return product

    async def create_product(
        self,
        *,
        name: str,
        slug: str | None,
        description: str | None,
        category_id: uuid.UUID,
        base_price_cents: int,
        attributes: dict[str, Any],
    ) -> ProductRecord:
        slug = slug or _slug_or_error(name, PRODUCT_INVALID_SLUG)
        async with self._uow() as uow:
            category = await uow.taxonomy.get_category(category_id)
            if category is None:
                raise CatalogError(CATEGORY_NOT_FOUND)
            if await uow.products.slug_exists(slug):
                raise CatalogError(PRODUCT_SLUG_TAKEN)
            product_id = await uow.products.add(
                slug=slug,
                name=name,
                description=description,
                category=category,
                base_price_cents=base_price_cents,
                attributes=attributes,
            )
            return await self._load(uow.products, product_id)

    async def update_product(
        self, product_id: uuid.UUID, version: int, fields: dict[str, Any]
    ) -> ProductRecord:
        async with self._uow() as uow:
            updates = dict(fields)
            if "category_id" in updates:
                category = await uow.taxonomy.get_category(updates["category_id"])
                if category is None:
                    raise CatalogError(CATEGORY_NOT_FOUND)
                updates["category_name_cache"] = category.name
            slug = updates.get("slug")
            if slug and await uow.products.slug_exists(slug, exclude=product_id):
                raise CatalogError(PRODUCT_SLUG_TAKEN)
            if not await uow.products.update_versioned(product_id, version, updates):
                if await uow.products.get(product_id) is None:
                    raise CatalogError(PRODUCT_NOT_FOUND)
                raise CatalogError(PRODUCT_VERSION_CONFLICT)
            if "base_price_cents" in updates:
                await uow.products.recompute_min_price(product_id)
            return await self._load(uow.products, product_id)

    async def generate_variants(
        self, product_id: uuid.UUID, colors: list[str], sizes: list[str]
    ) -> ProductRecord:
        async with self._uow() as uow:
            # Trava o produto: duas gerações simultâneas não disputam a mesma combinação.
            product = await uow.products.get(product_id, for_update=True)
            if product is None:
                raise CatalogError(PRODUCT_NOT_FOUND)
            unknown: dict[str, list[str]] = {}
            known_colors = await uow.products.known_colors(colors)
            known_sizes = await uow.products.known_sizes(sizes)
            bad_colors = [c for c in colors if c not in known_colors]
            bad_sizes = [s for s in sizes if s not in known_sizes]
            if bad_colors:
                unknown["colors"] = bad_colors
            if bad_sizes:
                unknown["sizes"] = bad_sizes
            if unknown:
                raise CatalogError(VARIANT_UNKNOWN_OPTION, unknown)
            existing = {(v.color_code, v.size_code) for v in product.variants}
            grid = generate_variant_grid(product_id, colors, sizes, existing)
            if grid:
                await uow.products.add_variants(product_id, grid)
                await uow.products.recompute_min_price(product_id)
            return await self._load(uow.products, product_id)

    async def update_variant(
        self, variant_id: uuid.UUID, version: int, fields: dict[str, Any]
    ) -> VariantRecord:
        async with self._uow() as uow:
            if not await uow.products.update_variant_versioned(variant_id, version, fields):
                if await uow.products.get_variant(variant_id) is None:
                    raise CatalogError(VARIANT_NOT_FOUND)
                raise CatalogError(VARIANT_VERSION_CONFLICT)
            variant = await uow.products.get_variant(variant_id)
            assert variant is not None  # noqa: S101
            await uow.products.recompute_min_price(variant.product_id)
            return variant

    # ------------------------------------------------------------------------ imagens

    async def add_image(
        self,
        product_id: uuid.UUID,
        *,
        data: bytes,
        ext: str,
        width: int,
        height: int,
        alt: str,
        color_code: str | None,
        credit_author: str | None,
        credit_source_url: str | None,
        license: str | None,  # noqa: A002
    ) -> tuple[ImageRecord, bool]:
        """Grava o arquivo e a linha. Devolve (imagem, criada); bytes repetidos no mesmo
        produto devolvem a imagem existente sem tocar em nada."""
        key = storage_key(data, ext)
        async with self._uow() as uow:
            # Trava o produto: dois uploads iguais simultâneos não duplicam a linha.
            product = await uow.products.get(product_id, for_update=True)
            if product is None:
                raise CatalogError(PRODUCT_NOT_FOUND)
            existing = next((i for i in product.images if i.storage_key == key), None)
            if existing is not None:
                # Regrava o arquivo (idempotente): refaz o volume de mídia se ele foi recriado.
                await self._storage.save(key, data)
                return existing, False
            await self._check_image_color(uow.products, color_code)
            await self._storage.save(key, data)
            position = max((i.position for i in product.images), default=-1) + 1
            image = await uow.products.add_image(
                product_id,
                storage_key=key,
                width=width,
                height=height,
                alt=alt,
                color_code=color_code,
                position=position,
                credit_author=credit_author,
                credit_source_url=credit_source_url,
                license=license,
            )
            return image, True

    async def update_image(self, image_id: uuid.UUID, fields: dict[str, Any]) -> ImageRecord:
        async with self._uow() as uow:
            if await uow.products.get_image(image_id) is None:
                raise CatalogError(IMAGE_NOT_FOUND)
            await self._check_image_color(uow.products, fields.get("color_code"))
            if fields:
                await uow.products.update_image(image_id, fields)
            image = await uow.products.get_image(image_id)
            assert image is not None  # noqa: S101
            return image

    async def delete_image(self, image_id: uuid.UUID) -> None:
        """Remove só a linha: o arquivo é endereçado por conteúdo e pode servir a outra linha."""
        async with self._uow() as uow:
            if not await uow.products.delete_image(image_id):
                raise CatalogError(IMAGE_NOT_FOUND)

    @staticmethod
    async def _check_image_color(products: ProductRepository, color_code: str | None) -> None:
        if color_code is not None and color_code not in await products.known_colors([color_code]):
            raise CatalogError(IMAGE_UNKNOWN_COLOR)

    async def publish(self, product_id: uuid.UUID) -> ProductRecord:
        async with self._uow() as uow:
            product = await uow.products.get(product_id, for_update=True)
            if product is None:
                raise CatalogError(PRODUCT_NOT_FOUND)
            check = PublishCheck(
                active_variant_prices=[
                    effective_price(product.base_price_cents, v.price_cents)
                    for v in product.variants
                    if v.active
                ],
                image_count=len(product.images),
            )
            blockers = publish_blockers(check)
            if blockers:
                raise CatalogError(PRODUCT_NOT_PUBLISHABLE, {"product": blockers})
            await uow.products.set_status(product_id, "active")
            return await self._load(uow.products, product_id)

    async def archive(self, product_id: uuid.UUID) -> ProductRecord:
        async with self._uow() as uow:
            if await uow.products.get(product_id, for_update=True) is None:
                raise CatalogError(PRODUCT_NOT_FOUND)
            await uow.products.set_status(product_id, "archived")
            return await self._load(uow.products, product_id)

    @staticmethod
    async def _load(products: ProductRepository, product_id: uuid.UUID) -> ProductRecord:
        product = await products.get(product_id)
        assert product is not None  # noqa: S101
        return product

    # ------------------------------------------------------------------------ estoque

    async def adjust_stock(
        self,
        variant_id: uuid.UUID,
        *,
        delta: int,
        reason: str,
        note: str | None,
        actor_id: uuid.UUID,
    ) -> tuple[MovementRecord, VariantRecord]:
        async with self._uow() as uow:
            # SELECT ... FOR UPDATE: ajustes concorrentes na mesma variante viram uma fila.
            variant = await uow.products.get_variant(variant_id, for_update=True)
            if variant is None:
                raise CatalogError(VARIANT_NOT_FOUND)
            try:
                new_on_hand = apply_adjustment(
                    variant.stock_on_hand, variant.stock_reserved, delta, reason
                )
            except StockError as exc:
                raise CatalogError(exc.code) from exc
            movement = await uow.stock.apply(variant_id, new_on_hand, delta, reason, note, actor_id)
            updated = await uow.products.get_variant(variant_id)
            assert updated is not None  # noqa: S101
            return movement, updated

    async def list_movements(
        self, variant_id: uuid.UUID, cursor: str | None, limit: int
    ) -> tuple[list[MovementRecord], str | None]:
        position = decode_movement_cursor(cursor) if cursor else None
        async with self._uow() as uow:
            if await uow.products.get_variant(variant_id) is None:
                raise CatalogError(VARIANT_NOT_FOUND)
            items = await uow.stock.list_movements(variant_id, position, limit + 1)
        if len(items) > limit:
            items = items[:limit]
            return items, encode_movement_cursor(items[-1])
        return items, None

    async def overview(self) -> Overview:
        async with self._uow() as uow:
            return await uow.stock.overview(RECENT_MOVEMENTS)

    # ------------------------------------------------------------------------ vitrine

    async def get_settings(self) -> dict[str, Any]:
        async with self._uow() as uow:
            data = await uow.settings.get()
        if data is None:
            raise CatalogError(SETTINGS_NOT_FOUND)
        return data

    async def put_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        async with self._uow() as uow:
            await uow.settings.put(data)
        return data
