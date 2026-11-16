from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager

import httpx
import pytest

from cart.main import create_app
from cart.settings import CartSettings

pytest_plugins = ["ks_platform.testing"]


@pytest.fixture
async def client(
    redis_url: str,
    asgi_client_factory: Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]],
) -> AsyncIterator[httpx.AsyncClient]:
    async with asgi_client_factory(
        create_app(CartSettings(redis_url=redis_url, client_secret="test-secret"))  # noqa: S106
    ) as http_client:
        yield http_client
