import httpx
from opentelemetry.propagate import inject


class _RetryOnceTransport(httpx.AsyncBaseTransport):
    """Repete uma vez GET que falhou ao conectar; outros métodos nunca repetem."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return await self._inner.handle_async_request(request)
        except httpx.ConnectError:
            if request.method != "GET":
                raise
            return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


async def _inject_traceparent(request: httpx.Request) -> None:
    inject(request.headers)


def make_http_client(
    base_url: str,
    timeout_s: float = 2.0,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """`transport` troca o transporte de rede (para testes); o retry continua aplicado."""
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout_s,
        transport=_RetryOnceTransport(transport or httpx.AsyncHTTPTransport()),
        event_hooks={"request": [_inject_traceparent]},
    )
