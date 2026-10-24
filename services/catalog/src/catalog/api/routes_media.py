"""Entrega pública das imagens (sem autenticação, cache imutável)."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from catalog.application.ports import ImageStorage
from catalog.domain.images import STORAGE_KEY_RE
from ks_platform.errors import ProblemError

router = APIRouter(prefix="/v1", tags=["media"])

_KEY = re.compile(STORAGE_KEY_RE)
_CONTENT_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
_CACHE = "public, max-age=31536000, immutable"


def image_storage(request: Request) -> ImageStorage:
    storage: ImageStorage = request.app.state.image_storage
    return storage


def _not_found() -> ProblemError:
    return ProblemError(404, "catalog.image.not_found", "Imagem não encontrada")


@router.get("/media/{storage_key:path}")
async def get_media(
    storage_key: str, storage: Annotated[ImageStorage, Depends(image_storage)]
) -> Response:
    # Chave fora do formato nunca chega ao disco.
    if not _KEY.fullmatch(storage_key):
        raise _not_found()
    data = await storage.read(storage_key)
    if data is None:
        raise _not_found()
    return Response(
        content=data,
        media_type=_CONTENT_TYPES[storage_key.rsplit(".", 1)[1]],
        headers={"Cache-Control": _CACHE, "X-Content-Type-Options": "nosniff"},
    )
