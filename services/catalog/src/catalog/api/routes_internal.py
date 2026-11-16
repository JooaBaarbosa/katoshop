"""Rotas internas serviço a serviço (token de serviço). Fora de /v1/admin e /v1/public."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.adapters import product_queries as queries
from catalog.api.schemas import InternalVariant
from catalog.application.admin_service import VARIANT_NOT_FOUND
from catalog.settings import CatalogSettings
from ks_platform.auth import ServicePrincipal, require_service
from ks_platform.errors import ProblemError

router = APIRouter(prefix="/v1/internal", tags=["internal"])


async def _session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


Session = Annotated[AsyncSession, Depends(_session)]
Service = Annotated[ServicePrincipal, Depends(require_service())]


@router.get("/variants/{variant_id}")
async def get_variant(
    variant_id: uuid.UUID, _service: Service, session: Session, request: Request
) -> InternalVariant:
    record = await queries.internal_variant(session, variant_id)
    if record is None:
        raise ProblemError(404, VARIANT_NOT_FOUND, "Variante não encontrada")
    settings: CatalogSettings = request.app.state.settings
    return InternalVariant.from_record(record, settings.public_base_url)
