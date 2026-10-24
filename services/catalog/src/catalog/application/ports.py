import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from catalog.domain.variants import NewVariant

# ---------------------------------------------------------------------------- registros


@dataclass(frozen=True)
class CategoryRecord:
    id: uuid.UUID
    slug: str
    name: str
    parent_id: uuid.UUID | None
    position: int


@dataclass(frozen=True)
class CollectionRecord:
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    featured: bool
    position: int
    product_ids: list[uuid.UUID]


@dataclass(frozen=True)
class VariantRecord:
    id: uuid.UUID
    product_id: uuid.UUID
    sku: str
    color_code: str
    size_code: str
    price_cents: int | None
    stock_on_hand: int
    stock_reserved: int
    version: int
    active: bool


@dataclass(frozen=True)
class ImageRecord:
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


@dataclass(frozen=True)
class ProductRecord:
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    category: CategoryRecord
    status: str
    base_price_cents: int
    min_price_cents: int | None
    attributes: dict[str, Any]
    version: int
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    variants: list[VariantRecord]
    images: list[ImageRecord]


@dataclass(frozen=True)
class ProductRow:
    id: uuid.UUID
    slug: str
    name: str
    status: str
    category: CategoryRecord
    min_price_cents: int | None
    variant_count: int
    total_available: int
    updated_at: datetime


@dataclass(frozen=True)
class ProductFilter:
    q: str | None = None
    status: str | None = None
    category_slug: str | None = None
    slug: str | None = None


@dataclass(frozen=True)
class ProductCursor:
    updated_at: datetime
    id: uuid.UUID


@dataclass(frozen=True)
class MovementRecord:
    id: uuid.UUID
    variant_id: uuid.UUID
    delta: int
    reason: str
    note: str | None
    actor_id: uuid.UUID | None
    created_at: datetime


@dataclass(frozen=True)
class MovementCursor:
    created_at: datetime
    id: uuid.UUID


@dataclass(frozen=True)
class RecentMovement:
    movement: MovementRecord
    sku: str
    product_id: uuid.UUID
    product_name: str


@dataclass(frozen=True)
class Overview:
    products_by_status: dict[str, int]
    out_of_stock_variants: int
    recent_movements: list[RecentMovement]


# ---------------------------------------------------------------------------- armazenamento


class ImageStorage(Protocol):
    async def save(self, key: str, data: bytes) -> None:
        """Grava de forma atômica e idempotente; `ValueError` se a chave for inválida."""
        ...

    async def read(self, key: str) -> bytes | None:
        """`None` se não existir; `ValueError` se a chave for inválida."""
        ...


# ---------------------------------------------------------------------------- repositórios


class TaxonomyRepository(Protocol):
    async def list_categories(self) -> list[CategoryRecord]: ...
    async def get_category(self, category_id: uuid.UUID) -> CategoryRecord | None: ...
    async def category_slug_exists(
        self, slug: str, *, exclude: uuid.UUID | None = None
    ) -> bool: ...
    async def add_category(
        self, slug: str, name: str, parent_id: uuid.UUID | None, position: int
    ) -> CategoryRecord: ...
    async def update_category(self, category_id: uuid.UUID, fields: dict[str, Any]) -> None: ...
    async def category_in_use(self, category_id: uuid.UUID) -> bool:
        """Verdadeiro se há produtos ou subcategorias vinculados."""
        ...

    async def delete_category(self, category_id: uuid.UUID) -> None: ...

    async def list_collections(self) -> list[CollectionRecord]: ...
    async def get_collection(self, collection_id: uuid.UUID) -> CollectionRecord | None: ...
    async def collection_slug_exists(
        self, slug: str, *, exclude: uuid.UUID | None = None
    ) -> bool: ...
    async def add_collection(
        self, slug: str, name: str, description: str | None, featured: bool, position: int
    ) -> CollectionRecord: ...
    async def update_collection(self, collection_id: uuid.UUID, fields: dict[str, Any]) -> None: ...
    async def delete_collection(self, collection_id: uuid.UUID) -> bool: ...
    async def set_collection_products(
        self, collection_id: uuid.UUID, product_ids: list[uuid.UUID]
    ) -> None: ...


class ProductRepository(Protocol):
    async def get(
        self, product_id: uuid.UUID, *, for_update: bool = False
    ) -> ProductRecord | None: ...
    async def slug_exists(self, slug: str, *, exclude: uuid.UUID | None = None) -> bool: ...
    async def existing_ids(self, product_ids: list[uuid.UUID]) -> set[uuid.UUID]: ...
    async def add(
        self,
        *,
        slug: str,
        name: str,
        description: str | None,
        category: CategoryRecord,
        base_price_cents: int,
        attributes: dict[str, Any],
    ) -> uuid.UUID: ...
    async def update_versioned(
        self, product_id: uuid.UUID, expected_version: int, fields: dict[str, Any]
    ) -> bool:
        """Aplica `fields` e incrementa `version` só se a versão bater; devolve se aplicou."""
        ...

    async def set_status(self, product_id: uuid.UUID, status: str) -> None:
        """Muda o status e incrementa `version`; ao ativar, preenche `published_at` uma vez."""
        ...

    async def refresh_category_cache(self, category_id: uuid.UUID, name: str) -> None: ...
    async def recompute_min_price(self, product_id: uuid.UUID) -> None: ...
    async def list(
        self, filters: ProductFilter, cursor: ProductCursor | None, limit: int
    ) -> list[ProductRow]: ...

    async def known_colors(self, codes: list[str]) -> set[str]: ...
    async def known_sizes(self, codes: list[str]) -> set[str]: ...
    async def add_variants(self, product_id: uuid.UUID, variants: list[NewVariant]) -> None: ...
    async def get_variant(
        self, variant_id: uuid.UUID, *, for_update: bool = False
    ) -> VariantRecord | None: ...
    async def update_variant_versioned(
        self, variant_id: uuid.UUID, expected_version: int, fields: dict[str, Any]
    ) -> bool: ...

    async def add_image(
        self,
        product_id: uuid.UUID,
        *,
        storage_key: str,
        width: int,
        height: int,
        alt: str,
        color_code: str | None,
        position: int,
        credit_author: str | None,
        credit_source_url: str | None,
        license: str | None,
    ) -> ImageRecord: ...
    async def get_image(self, image_id: uuid.UUID) -> ImageRecord | None: ...
    async def update_image(self, image_id: uuid.UUID, fields: dict[str, Any]) -> None: ...
    async def delete_image(self, image_id: uuid.UUID) -> bool:
        """Remove só a linha; o arquivo é endereçado por conteúdo e pode ser compartilhado."""
        ...


class StockRepository(Protocol):
    async def apply(
        self,
        variant_id: uuid.UUID,
        new_on_hand: int,
        delta: int,
        reason: str,
        note: str | None,
        actor_id: uuid.UUID,
    ) -> MovementRecord:
        """Grava o movimento e o novo saldo na transação corrente (variante já travada)."""
        ...

    async def list_movements(
        self, variant_id: uuid.UUID, cursor: MovementCursor | None, limit: int
    ) -> list[MovementRecord]: ...
    async def overview(self, recent_limit: int) -> Overview: ...


class SettingsRepository(Protocol):
    async def get(self) -> dict[str, Any] | None: ...
    async def put(self, data: dict[str, Any]) -> None: ...


class CatalogUnitOfWork(Protocol):
    """Repositórios que compartilham uma única sessão e transação."""

    @property
    def taxonomy(self) -> TaxonomyRepository: ...
    @property
    def products(self) -> ProductRepository: ...
    @property
    def stock(self) -> StockRepository: ...
    @property
    def settings(self) -> SettingsRepository: ...


type UnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[CatalogUnitOfWork]]
