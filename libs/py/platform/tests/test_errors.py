import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.exc import DBAPIError

from ks_platform.errors import ProblemError, install_db_error_handler, install_problem_handlers


class Payload(BaseModel):
    email: str


def make_app() -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)

    @app.get("/conflict")
    async def conflict() -> None:
        raise ProblemError(409, "x.y.z", "Conflito")

    @app.get("/auth")
    async def auth() -> None:
        raise ProblemError(401, "auth.x", "Nao", headers={"WWW-Authenticate": "Bearer"})

    @app.post("/items")
    async def items(payload: Payload) -> Payload:
        return payload

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("segredo")

    return app


async def test_problem_error_rendered(asgi_client_factory):
    async with asgi_client_factory(make_app()) as c:
        response = await c.get("/conflict")
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "x.y.z"
    assert body["title"] == "Conflito"
    assert body["type"] == "about:blank"
    assert body["trace_id"] is None


async def test_validation_error_maps_fields(asgi_client_factory):
    async with asgi_client_factory(make_app()) as c:
        response = await c.post("/items", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "request.validation"
    assert "body.email" in body["errors"]


async def test_http_exception_mapped(asgi_client_factory):
    async with asgi_client_factory(make_app()) as c:
        response = await c.get("/nao-existe")
    assert response.status_code == 404
    assert response.json()["code"] == "http.404"
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_unhandled_error_hides_details(asgi_client_factory):
    async with asgi_client_factory(make_app()) as c:
        response = await c.get("/boom")
    assert response.status_code == 500
    assert "segredo" not in response.text
    assert response.json()["code"] == "internal.error"


async def test_http_exception_keeps_headers(asgi_client_factory):
    async with asgi_client_factory(make_app()) as c:
        response = await c.post("/conflict")
    assert response.status_code == 405
    assert "GET" in response.headers["allow"]
    assert response.json()["code"] == "http.405"


async def test_problem_error_headers_forwarded(asgi_client_factory):
    async with asgi_client_factory(make_app()) as c:
        response = await c.get("/auth")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


class _FakeDriverError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(f"sqlstate {sqlstate}")
        self.sqlstate = sqlstate


def make_db_app() -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)
    install_db_error_handler(app)

    @app.get("/db/{sqlstate}")
    async def db_error(sqlstate: str) -> None:
        raise DBAPIError("SELECT 1", {}, _FakeDriverError(sqlstate))

    return app


@pytest.mark.parametrize("sqlstate", ["22021", "22008", "22P05"])
async def test_db_input_errors_map_to_422(asgi_client_factory, sqlstate):
    async with asgi_client_factory(make_db_app()) as c:
        response = await c.get(f"/db/{sqlstate}")
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "request.validation"
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_other_db_errors_stay_500_and_propagate(asgi_client_factory):
    async with asgi_client_factory(make_db_app()) as c:
        response = await c.get("/db/22012")
    assert response.status_code == 500
    assert response.json()["code"] == "internal.error"
    # O erro precisa chegar ao ServerErrorMiddleware (traceback no log, exceção no span).
    transport = httpx.ASGITransport(make_db_app(), raise_app_exceptions=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as raw:
        with pytest.raises(DBAPIError) as raised:
            await raw.get("/db/22012")
    assert getattr(raised.value.orig, "sqlstate", None) == "22012"
