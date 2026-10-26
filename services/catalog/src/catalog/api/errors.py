import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from sqlalchemy.exc import DBAPIError
from starlette.responses import Response

from catalog.application import admin_service as codes
from catalog.application.admin_service import CatalogError
from ks_platform.errors import ProblemError

# SQLSTATEs causados por entrada do cliente que escapou da validação: byte inválido (ex.: NUL)
# e data/hora fora do intervalo. Viram 422; qualquer outro erro do banco segue como 500.
DB_INPUT_SQLSTATES = frozenset({"22021", "22008"})

type _Handler = Callable[[Request, Any], Response | Awaitable[Response]]


async def _run(handler: _Handler, request: Request, exc: Exception) -> Response:
    result = handler(request, exc)
    return await result if inspect.isawaitable(result) else result


def install_db_error_handler(app: FastAPI) -> None:
    """Chame depois de `install_problem_handlers`: reaproveita os handlers já registrados."""

    async def _db_error(request: Request, exc: Exception) -> Response:
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
        if sqlstate in DB_INPUT_SQLSTATES:
            problem = ProblemError(422, "request.validation", "Requisição inválida")
            return await _run(app.exception_handlers[ProblemError], request, problem)
        # Demais erros sobem ao ServerErrorMiddleware: traceback no log, exceção no span e
        # corpo 500 `internal.error` pelo handler da plataforma, como antes deste handler.
        raise exc

    app.add_exception_handler(DBAPIError, _db_error)


_STATUS: dict[str, tuple[int, str]] = {
    codes.CATEGORY_NOT_FOUND: (404, "Categoria não encontrada"),
    codes.CATEGORY_SLUG_TAKEN: (409, "Slug de categoria já usado"),
    codes.CATEGORY_IN_USE: (409, "Categoria em uso"),
    codes.CATEGORY_INVALID_SLUG: (422, "Nome não gera slug válido"),
    codes.COLLECTION_NOT_FOUND: (404, "Coleção não encontrada"),
    codes.COLLECTION_SLUG_TAKEN: (409, "Slug de coleção já usado"),
    codes.COLLECTION_INVALID_SLUG: (422, "Nome não gera slug válido"),
    codes.COLLECTION_DUPLICATE_PRODUCT: (422, "Produto repetido na coleção"),
    codes.PRODUCT_NOT_FOUND: (404, "Produto não encontrado"),
    codes.PRODUCT_SLUG_TAKEN: (409, "Slug de produto já usado"),
    codes.PRODUCT_INVALID_SLUG: (422, "Nome não gera slug válido"),
    codes.PRODUCT_VERSION_CONFLICT: (409, "Produto alterado por outra pessoa"),
    codes.PRODUCT_NOT_PUBLISHABLE: (422, "Produto não pode ser publicado"),
    codes.VARIANT_NOT_FOUND: (404, "Variante não encontrada"),
    codes.VARIANT_VERSION_CONFLICT: (409, "Variante alterada por outra pessoa"),
    codes.VARIANT_UNKNOWN_OPTION: (422, "Cor ou tamanho inexistente"),
    codes.CATEGORY_PARENT_CYCLE: (422, "Categoria não pode descender de si mesma"),
    codes.SETTINGS_NOT_FOUND: (404, "Configurações da vitrine ainda não definidas"),
    codes.IMAGE_NOT_FOUND: (404, "Imagem não encontrada"),
    codes.IMAGE_UNKNOWN_COLOR: (422, "Cor inexistente"),
    "catalog.stock.invalid_reason": (422, "Motivo de ajuste inválido"),
    "catalog.stock.zero_delta": (422, "Ajuste sem quantidade"),
    "catalog.stock.would_go_negative": (422, "Estoque ficaria negativo"),
}


def to_problem(error: CatalogError) -> ProblemError:
    status, title = _STATUS.get(error.code, (422, "Operação inválida"))
    return ProblemError(status, error.code, title, errors=error.errors)


async def mapped[T](call: Awaitable[T]) -> T:
    try:
        return await call
    except CatalogError as exc:
        raise to_problem(exc) from exc
