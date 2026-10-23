import logging

from fastapi import FastAPI

from ks_platform.health import health_router


def make_app(result: bool | Exception) -> FastAPI:
    async def check() -> bool:
        if isinstance(result, Exception):
            raise result
        return result

    app = FastAPI()
    app.include_router(health_router(check))
    return app


async def test_live_ok(asgi_client_factory):
    async with asgi_client_factory(make_app(True)) as c:
        response = await c.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_ok(asgi_client_factory):
    async with asgi_client_factory(make_app(True)) as c:
        response = await c.get("/health/ready")
    assert response.status_code == 200


async def test_ready_returns_503_when_check_fails(asgi_client_factory):
    async with asgi_client_factory(make_app(False)) as c:
        response = await c.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


async def test_ready_returns_503_when_check_raises(asgi_client_factory):
    async with asgi_client_factory(make_app(ConnectionError("db"))) as c:
        response = await c.get("/health/ready")
    assert response.status_code == 503


async def test_ready_logs_when_check_raises(asgi_client_factory, caplog):
    with caplog.at_level(logging.WARNING, logger="ks_platform.health"):
        async with asgi_client_factory(make_app(ConnectionError("db"))) as c:
            response = await c.get("/health/ready")
    assert response.text == '{"status":"unavailable"}'
    assert any("ready_check failed" in r.message and r.exc_info for r in caplog.records)
