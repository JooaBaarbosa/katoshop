from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import httpx

from cart.main import create_app
from cart.settings import CartSettings


async def test_live(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health/live")).status_code == 200


async def test_ready_ok_with_redis(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_ready_503_when_redis_down(
    asgi_client_factory: Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    app = create_app(CartSettings(redis_url="redis://127.0.0.1:1/0", client_secret="x"))  # noqa: S106
    async with asgi_client_factory(app) as http_client:
        resp = await http_client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "unavailable"}
