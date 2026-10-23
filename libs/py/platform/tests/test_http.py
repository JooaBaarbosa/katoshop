import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider

from ks_platform.http import make_http_client


def _client(handler) -> httpx.AsyncClient:
    return make_http_client("http://svc", transport=httpx.MockTransport(handler))


async def test_http_client_propagates_traceparent():
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("traceparent"))
        return httpx.Response(200)

    tracer = TracerProvider().get_tracer("t")
    async with _client(handler) as client:
        with tracer.start_as_current_span("s") as span:
            await client.get("/x")
    trace_id = format(span.get_span_context().trace_id, "032x")
    assert seen[0] is not None
    assert seen[0].split("-")[1] == trace_id


async def test_http_client_retries_get_once_on_connect_error():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200)

    async with _client(handler) as client:
        response = await client.get("/x")
    assert response.status_code == 200
    assert calls == 2


async def test_http_client_gives_up_after_one_retry():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("boom", request=request)

    async with _client(handler) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get("/x")
    assert calls == 2


async def test_http_client_does_not_retry_post():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("boom", request=request)

    async with _client(handler) as client:
        with pytest.raises(httpx.ConnectError):
            await client.post("/x")
    assert calls == 1
