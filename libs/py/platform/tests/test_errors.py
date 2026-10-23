import httpx
from fastapi import FastAPI
from httpx import ASGITransport
from pydantic import BaseModel

from ks_platform.errors import ProblemError, install_problem_handlers


class Payload(BaseModel):
    email: str


def make_app() -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)

    @app.get("/conflict")
    async def conflict() -> None:
        raise ProblemError(409, "x.y.z", "Conflito")

    @app.post("/items")
    async def items(payload: Payload) -> Payload:
        return payload

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("segredo")

    return app


def client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=ASGITransport(app, raise_app_exceptions=False), base_url="http://test"
    )


async def test_problem_error_rendered():
    async with client(make_app()) as c:
        response = await c.get("/conflict")
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "x.y.z"
    assert body["title"] == "Conflito"
    assert body["type"] == "about:blank"
    assert body["trace_id"] is None


async def test_validation_error_maps_fields():
    async with client(make_app()) as c:
        response = await c.post("/items", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "request.validation"
    assert "body.email" in body["errors"]


async def test_http_exception_mapped():
    async with client(make_app()) as c:
        response = await c.get("/nao-existe")
    assert response.status_code == 404
    assert response.json()["code"] == "http.404"
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_unhandled_error_hides_details():
    async with client(make_app()) as c:
        response = await c.get("/boom")
    assert response.status_code == 500
    assert "segredo" not in response.text
    assert response.json()["code"] == "internal.error"
