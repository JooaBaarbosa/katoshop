"""Rotas públicas da vitrine: sem autenticação, com cache HTTP curto."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.adapters import product_queries as queries
from catalog.adapters.product_queries import ProductFilter, SortOrder
from catalog.api.errors import mapped
from catalog.api.schemas import (
    CreditList,
    FacetsOut,
    ProductCardOut,
    ProductCardPage,
    ProductDetailOut,
    PublicCategoryList,
    PublicCollection,
    PublicCollectionList,
)
from catalog.application.admin_service import (
    COLLECTION_NOT_FOUND,
    PRODUCT_NOT_FOUND,
    AdminCatalogService,
)
from catalog.domain.settings_schema import StorefrontSettings
from catalog.settings import CatalogSettings
from ks_platform.errors import ProblemError

router = APIRouter(prefix="/v1", tags=["public"])

CACHE_CONTROL = "public, max-age=30"
_INT4_MAX = 2**31 - 1

# Sem max_length no cursor: o decode devolve o código próprio de cursor inválido.
Cursor = Annotated[str | None, Query()]
Limit = Annotated[int, Query(ge=1, le=100)]
SlugParam = Annotated[str | None, Query(max_length=160)]
Codes = Annotated[list[str], Query(max_length=20)]
Price = Annotated[int | None, Query(ge=0, le=_INT4_MAX)]


async def db_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


def media_base(request: Request) -> str:
    settings: CatalogSettings = request.app.state.settings
    return settings.public_base_url


def admin_service(request: Request) -> AdminCatalogService:
    service: AdminCatalogService = request.app.state.admin_service
    return service


Session = Annotated[AsyncSession, Depends(db_session)]
MediaBase = Annotated[str, Depends(media_base)]
Service = Annotated[AdminCatalogService, Depends(admin_service)]


def product_filter(
    category: SlugParam = None,
    collection: SlugParam = None,
    size: Codes = [],  # noqa: B006 - o FastAPI copia o padrão por requisição
    color: Codes = [],  # noqa: B006
    price_min: Price = None,
    price_max: Price = None,
    q: str | None = None,
    sort: SortOrder = "relevance",
) -> ProductFilter:
    return ProductFilter(
        category=category,
        collection=collection,
        sizes=tuple(size),
        colors=tuple(color),
        price_min=price_min,
        price_max=price_max,
        q=q,
        sort=sort,
    )


Filter = Annotated[ProductFilter, Depends(product_filter)]


@router.get("/products")
async def list_products(
    f: Filter,
    session: Session,
    base: MediaBase,
    response: Response,
    cursor: Cursor = None,
    limit: Limit = 24,
) -> ProductCardPage:
    page = await queries.list_products(session, f, cursor, limit)
    response.headers["Cache-Control"] = CACHE_CONTROL
    return ProductCardPage(
        items=[ProductCardOut.from_record(card, base) for card in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/products/facets")
async def product_facets(f: Filter, session: Session, response: Response) -> FacetsOut:
    result = await queries.facets(session, f)
    response.headers["Cache-Control"] = CACHE_CONTROL
    return FacetsOut.from_record(result)


@router.get("/products/{slug}")
async def product_detail(
    slug: str, session: Session, base: MediaBase, response: Response
) -> ProductDetailOut:
    detail = await queries.product_detail(session, slug)
    if detail is None:
        raise ProblemError(404, PRODUCT_NOT_FOUND, "Produto não encontrado")
    response.headers["Cache-Control"] = CACHE_CONTROL
    return ProductDetailOut.from_record(detail, base)


@router.get("/categories")
async def list_categories(service: Service, response: Response) -> PublicCategoryList:
    categories = await service.list_categories()
    response.headers["Cache-Control"] = CACHE_CONTROL
    return PublicCategoryList.from_records(categories)


@router.get("/collections")
async def list_collections(service: Service, response: Response) -> PublicCollectionList:
    collections = await service.list_collections()
    response.headers["Cache-Control"] = CACHE_CONTROL
    return PublicCollectionList(items=[PublicCollection.from_record(c) for c in collections])


@router.get("/collections/{slug}")
async def get_collection(slug: str, service: Service, response: Response) -> PublicCollection:
    # Poucas coleções por loja: filtrar a lista evita uma consulta só para isso.
    found = [c for c in await service.list_collections() if c.slug == slug]
    if not found:
        raise ProblemError(404, COLLECTION_NOT_FOUND, "Coleção não encontrada")
    response.headers["Cache-Control"] = CACHE_CONTROL
    return PublicCollection.from_record(found[0])


@router.get("/storefront/settings")
async def storefront_settings(service: Service, response: Response) -> StorefrontSettings:
    data = await mapped(service.get_settings())
    response.headers["Cache-Control"] = CACHE_CONTROL
    return StorefrontSettings.model_validate(data)


@router.get("/credits")
async def credits(session: Session, base: MediaBase, response: Response) -> CreditList:
    result = await queries.list_credits(session)
    response.headers["Cache-Control"] = CACHE_CONTROL
    return CreditList.from_records(result, base)
