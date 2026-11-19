from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

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


async def test_injected_redis_client_is_not_closed_by_lifespan(
    redis_url: str,
    asgi_client_factory: Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    from redis.asyncio import Redis  # noqa: PLC0415

    class Spy(Redis):
        closed = 0

        async def aclose(self, *args: Any, **kwargs: Any) -> None:
            Spy.closed += 1
            await super().aclose(*args, **kwargs)

    shared = Spy.from_url(redis_url)
    settings = CartSettings(redis_url=redis_url, client_secret="x")  # noqa: S106
    async with asgi_client_factory(create_app(settings, redis_client=shared)) as http_client:
        assert (await http_client.get("/health/ready")).status_code == 200
    assert Spy.closed == 0
    await shared.aclose()


async def test_lifespan_closes_owned_upstream_clients(
    redis_url: str,
    asgi_client_factory: Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    app = create_app(CartSettings(redis_url=redis_url, client_secret="x"))  # noqa: S106
    async with asgi_client_factory(app) as http_client:
        assert (await http_client.get("/health/live")).status_code == 200
    upstreams = [app.state.catalog, app.state.promotions]
    clients: list[httpx.AsyncClient] = [u._http for u in upstreams]
    clients += [u._tokens._http for u in upstreams]
    assert all(c.is_closed for c in clients)
