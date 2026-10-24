import asyncio
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from catalog.adapters.image_probe import InvalidImageError, probe_image
from catalog.api.errors import mapped
from catalog.api.schemas import (
    AdminImage,
    AdminProduct,
    AdminProductRow,
    AdminVariant,
    CategoryIn,
    CategoryList,
    CategoryOut,
    CategoryPatch,
    CollectionIn,
    CollectionList,
    CollectionOut,
    CollectionPatch,
    CollectionProductsIn,
    GenerateVariantsIn,
    ImagePatch,
    ImageUploadIn,
    MovementOut,
    MovementPage,
    OverviewOut,
    ProductIn,
    ProductPage,
    ProductPatch,
    ProductStatus,
    StockAdjustmentIn,
    StockAdjustmentOut,
    VariantPatch,
    variant_out,
)
from catalog.application.admin_service import AdminCatalogService
from catalog.application.ports import ProductFilter
from catalog.domain.images import MAX_IMAGE_BYTES, detect_image_type
from catalog.domain.settings_schema import StorefrontSettings
from catalog.settings import CatalogSettings
from ks_platform.auth import Principal, require_permission
from ks_platform.errors import ProblemError

# Mesmo objeto na dependência do router e nas rotas: o FastAPI verifica o token uma vez só.
catalog_writer = require_permission("catalog.write")

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(catalog_writer)])

Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=512)]


def admin_service(request: Request) -> AdminCatalogService:
    service: AdminCatalogService = request.app.state.admin_service
    return service


def media_base(request: Request) -> str:
    settings: CatalogSettings = request.app.state.settings
    return settings.public_base_url


Service = Annotated[AdminCatalogService, Depends(admin_service)]
MediaBase = Annotated[str, Depends(media_base)]
Writer = Annotated[Principal, Depends(catalog_writer)]

# ---------------------------------------------------------------------------- categorias


@router.get("/categories")
async def list_categories(service: Service) -> CategoryList:
    categories = await service.list_categories()
    return CategoryList(items=[CategoryOut.from_record(c) for c in categories])


@router.post("/categories", status_code=201)
async def create_category(body: CategoryIn, service: Service) -> CategoryOut:
    category = await mapped(
        service.create_category(body.name, body.slug, body.parent_id, body.position)
    )
    return CategoryOut.from_record(category)


@router.patch("/categories/{category_id}")
async def update_category(
    category_id: uuid.UUID, body: CategoryPatch, service: Service
) -> CategoryOut:
    category = await mapped(service.update_category(category_id, body.changes()))
    return CategoryOut.from_record(category)


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(category_id: uuid.UUID, service: Service) -> Response:
    await mapped(service.delete_category(category_id))
    return Response(status_code=204)


# ---------------------------------------------------------------------------- coleções


@router.get("/collections")
async def list_collections(service: Service) -> CollectionList:
    collections = await service.list_collections()
    return CollectionList(items=[CollectionOut.from_record(c) for c in collections])


@router.post("/collections", status_code=201)
async def create_collection(body: CollectionIn, service: Service) -> CollectionOut:
    collection = await mapped(
        service.create_collection(
            body.name, body.slug, body.description, body.featured, body.position
        )
    )
    return CollectionOut.from_record(collection)


@router.patch("/collections/{collection_id}")
async def update_collection(
    collection_id: uuid.UUID, body: CollectionPatch, service: Service
) -> CollectionOut:
    collection = await mapped(service.update_collection(collection_id, body.changes()))
    return CollectionOut.from_record(collection)


@router.delete("/collections/{collection_id}", status_code=204)
async def delete_collection(collection_id: uuid.UUID, service: Service) -> Response:
    await mapped(service.delete_collection(collection_id))
    return Response(status_code=204)


@router.put("/collections/{collection_id}/products")
async def set_collection_products(
    collection_id: uuid.UUID, body: CollectionProductsIn, service: Service
) -> CollectionOut:
    collection = await mapped(service.set_collection_products(collection_id, body.product_ids))
    return CollectionOut.from_record(collection)


# ---------------------------------------------------------------------------- produtos


@router.get("/products")
async def list_products(
    service: Service,
    q: Annotated[str | None, Query(max_length=200)] = None,
    status: ProductStatus | None = None,
    category: Annotated[str | None, Query(max_length=120)] = None,
    slug: Annotated[str | None, Query(max_length=160)] = None,
    cursor: Cursor = None,
    limit: Limit = 24,
) -> ProductPage:
    filters = ProductFilter(q=q, status=status, category_slug=category, slug=slug)
    rows, next_cursor = await mapped(service.list_products(filters, cursor, limit))
    return ProductPage(
        items=[AdminProductRow.from_record(r) for r in rows], next_cursor=next_cursor
    )


@router.post("/products", status_code=201)
async def create_product(body: ProductIn, service: Service, base: MediaBase) -> AdminProduct:
    product = await mapped(
        service.create_product(
            name=body.name,
            slug=body.slug,
            description=body.description,
            category_id=body.category_id,
            base_price_cents=body.base_price_cents,
            attributes=body.attributes,
        )
    )
    return AdminProduct.from_record(product, base)


@router.get("/products/{product_id}")
async def get_product(product_id: uuid.UUID, service: Service, base: MediaBase) -> AdminProduct:
    return AdminProduct.from_record(await mapped(service.get_product(product_id)), base)


@router.patch("/products/{product_id}")
async def update_product(
    product_id: uuid.UUID, body: ProductPatch, service: Service, base: MediaBase
) -> AdminProduct:
    fields = body.changes(exclude=frozenset({"version"}))
    product = await mapped(service.update_product(product_id, body.version, fields))
    return AdminProduct.from_record(product, base)


@router.post("/products/{product_id}/variants/generate")
async def generate_variants(
    product_id: uuid.UUID, body: GenerateVariantsIn, service: Service, base: MediaBase
) -> AdminProduct:
    product = await mapped(service.generate_variants(product_id, body.colors, body.sizes))
    return AdminProduct.from_record(product, base)


@router.post("/products/{product_id}/publish")
async def publish_product(product_id: uuid.UUID, service: Service, base: MediaBase) -> AdminProduct:
    return AdminProduct.from_record(await mapped(service.publish(product_id)), base)


@router.post("/products/{product_id}/archive")
async def archive_product(product_id: uuid.UUID, service: Service, base: MediaBase) -> AdminProduct:
    return AdminProduct.from_record(await mapped(service.archive(product_id)), base)


@router.patch("/variants/{variant_id}")
async def update_variant(
    variant_id: uuid.UUID, body: VariantPatch, service: Service
) -> AdminVariant:
    fields = body.changes(exclude=frozenset({"version"}))
    return variant_out(await mapped(service.update_variant(variant_id, body.version, fields)))


# ---------------------------------------------------------------------------- imagens

_READ_CHUNK = 64 * 1024
# Folga para o envelope multipart (nomes de campos, limites) acima dos bytes do arquivo.
_MULTIPART_OVERHEAD = 1024 * 1024


def _unsupported() -> ProblemError:
    return ProblemError(
        415, "catalog.image.unsupported_type", "Envie uma imagem JPEG, PNG ou WebP válida"
    )


def _too_large() -> ProblemError:
    return ProblemError(413, "catalog.image.too_large", "Imagem maior que 8 MB")


async def _read_limited(file: UploadFile) -> tuple[bytes, str]:
    """Lê no máximo MAX_IMAGE_BYTES + 1 bytes, em pedaços; tipo pelos primeiros bytes."""
    head = await file.read(12)
    ext = detect_image_type(head)
    if ext is None:
        raise _unsupported()
    chunks = [head]
    total = len(head)
    while total <= MAX_IMAGE_BYTES:
        chunk = await file.read(min(_READ_CHUNK, MAX_IMAGE_BYTES + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    if total > MAX_IMAGE_BYTES:
        raise _too_large()
    return b"".join(chunks), ext


def _text(value: object) -> str | None:
    """Campo de formulário vazio equivale a ausente."""
    return value if isinstance(value, str) and value.strip() else None


_UPLOAD_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file", "alt"],
                    "properties": {
                        "file": {"type": "string", "format": "binary"},
                        "alt": {"type": "string", "minLength": 1, "maxLength": 300},
                        "color_code": {"type": "string"},
                        "credit_author": {"type": "string"},
                        "credit_source_url": {"type": "string", "format": "uri"},
                        "license": {"type": "string"},
                    },
                }
            }
        },
    }
}


@router.post(
    "/products/{product_id}/images",
    status_code=201,
    openapi_extra=_UPLOAD_BODY,
    responses={200: {"model": AdminImage, "description": "imagem já existente"}},
)
async def upload_image(
    product_id: uuid.UUID,
    request: Request,
    response: Response,
    service: Service,
    base: MediaBase,
) -> AdminImage:
    # O multipart é lido aqui (e não por File/Form) para que a autenticação rode antes de
    # qualquer byte do corpo ser aceito, e para recusar tamanho declarado absurdo cedo.
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit():
        if int(declared) > MAX_IMAGE_BYTES + _MULTIPART_OVERHEAD:
            raise _too_large()
    form = await request.form(max_files=1, max_fields=10)
    try:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise ProblemError(
                422,
                "request.validation",
                "Requisição inválida",
                errors={"file": ["campo obrigatório"]},
            )
        alt = _text(form.get("alt"))
        if alt is None:
            raise ProblemError(
                422, "catalog.image.alt_required", "O texto alternativo da imagem é obrigatório"
            )
        try:
            fields = ImageUploadIn(
                color_code=_text(form.get("color_code")),
                credit_author=_text(form.get("credit_author")),
                credit_source_url=_text(form.get("credit_source_url")),
                license=_text(form.get("license")),
            )
        except ValidationError as exc:
            errors: dict[str, list[str]] = {}
            for err in exc.errors():
                errors.setdefault(str(err["loc"][0]), []).append(err["msg"])
            raise ProblemError(
                422, "request.validation", "Requisição inválida", errors=errors
            ) from exc
        data, ext = await _read_limited(file)
    finally:
        await form.close()
    try:
        width, height = await asyncio.to_thread(probe_image, data)
    except InvalidImageError as exc:
        raise _unsupported() from exc
    image, created = await mapped(
        service.add_image(
            product_id,
            data=data,
            ext=ext,
            width=width,
            height=height,
            alt=alt.strip(),
            color_code=fields.color_code,
            credit_author=fields.credit_author,
            credit_source_url=fields.credit_source_url,
            license=fields.license,
        )
    )
    if not created:
        response.status_code = 200
    return AdminImage.from_record(image, base)


@router.patch("/images/{image_id}")
async def update_image(
    image_id: uuid.UUID, body: ImagePatch, service: Service, base: MediaBase
) -> AdminImage:
    image = await mapped(service.update_image(image_id, body.changes()))
    return AdminImage.from_record(image, base)


@router.delete("/images/{image_id}", status_code=204)
async def delete_image(image_id: uuid.UUID, service: Service) -> Response:
    await mapped(service.delete_image(image_id))
    return Response(status_code=204)


# ---------------------------------------------------------------------------- estoque


@router.post("/variants/{variant_id}/stock-adjustments", status_code=201)
async def adjust_stock(
    variant_id: uuid.UUID, body: StockAdjustmentIn, service: Service, principal: Writer
) -> StockAdjustmentOut:
    movement, variant = await mapped(
        service.adjust_stock(
            variant_id,
            delta=body.delta,
            reason=body.reason,
            note=body.note,
            actor_id=principal.user_id,
        )
    )
    return StockAdjustmentOut(
        movement=MovementOut.from_record(movement), variant=variant_out(variant)
    )


@router.get("/variants/{variant_id}/stock-movements")
async def list_stock_movements(
    variant_id: uuid.UUID, service: Service, cursor: Cursor = None, limit: Limit = 24
) -> MovementPage:
    items, next_cursor = await mapped(service.list_movements(variant_id, cursor, limit))
    return MovementPage(items=[MovementOut.from_record(m) for m in items], next_cursor=next_cursor)


@router.get("/overview")
async def overview(service: Service) -> OverviewOut:
    return OverviewOut.from_overview(await service.overview())


# ---------------------------------------------------------------------------- vitrine


@router.get("/storefront/settings")
async def get_storefront_settings(service: Service) -> StorefrontSettings:
    return StorefrontSettings.model_validate(await mapped(service.get_settings()))


@router.put("/storefront/settings")
async def put_storefront_settings(body: StorefrontSettings, service: Service) -> StorefrontSettings:
    data: dict[str, Any] = body.model_dump(mode="json")
    return StorefrontSettings.model_validate(await service.put_settings(data))
