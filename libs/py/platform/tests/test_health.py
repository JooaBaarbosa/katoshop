import httpx
from fastapi import FastAPI
from httpx import ASGITransport

from ks_platform.health import health_router


def make_client(result: bool | Exception) -> httpx.AsyncClient:
    async def check() -> bool:
        if isinstance(result, Exception):
            raise result
        return result

    app = FastAPI()
    app.include_router(health_router(check))
    return httpx.AsyncClient(transport=ASGITransport(app), base_url="http://test")


async def test_live_ok():
    async with make_client(True) as c:
        response = await c.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_ok():
    async with make_client(True) as c:
        response = await c.get("/health/ready")
    assert response.status_code == 200


async def test_ready_returns_503_when_check_fails():
    async with make_client(False) as c:
        response = await c.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


async def test_ready_returns_503_when_check_raises():
    async with make_client(ConnectionError("db")) as c:
        response = await c.get("/health/ready")
    assert response.status_code == 503
