import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import trace
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

PROBLEM_MEDIA_TYPE = "application/problem+json"


class ProblemError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str | None = None,
        errors: dict[str, list[str]] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(title)
        self.headers = headers
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.errors = errors


def _trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x")


def _problem(
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    errors: dict[str, list[str]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, object] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "trace_id": _trace_id(),
    }
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE, headers=headers)


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem_error(_: Request, exc: ProblemError) -> JSONResponse:
        return _problem(exc.status, exc.code, exc.title, exc.detail, exc.errors, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors: dict[str, list[str]] = {}
        for err in exc.errors():
            path = ".".join(str(part) for part in err["loc"])
            errors.setdefault(path, []).append(err["msg"])
        return _problem(422, "request.validation", "Requisição inválida", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else None
        return _problem(
            exc.status_code,
            f"http.{exc.status_code}",
            detail or "Erro",
            detail,
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, __: Exception) -> JSONResponse:
        return _problem(500, "internal.error", "Erro interno")


# SQLSTATEs causados por entrada do cliente que escapou da validação: byte inválido (ex.: NUL),
# data/hora fora do intervalo e caractere sem tradução (ex.: \u0000 em jsonb). Viram 422;
# qualquer outro erro do banco segue como 500.
DB_INPUT_SQLSTATES = frozenset({"22021", "22008", "22P05"})

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
        # corpo 500 `internal.error` pelo handler `Exception` acima.
        raise exc

    app.add_exception_handler(DBAPIError, _db_error)
