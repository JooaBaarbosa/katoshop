# ruff: noqa: S105, S106
import json
import logging

import pytest
import structlog
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.metrics import _internal as metrics_internal
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from pydantic_settings import SettingsConfigDict

from ks_platform import observability
from ks_platform.observability import (
    build_providers,
    configure_logging,
    configure_observability,
)
from ks_platform.settings import BaseServiceSettings


def _last_json(capsys) -> dict[str, object]:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return json.loads(lines[-1])


def test_log_contains_trace_id(capsys):
    configure_logging("svc", "INFO")
    tracer = TracerProvider().get_tracer("t")
    with tracer.start_as_current_span("s"):
        structlog.get_logger().info("x")
    data = _last_json(capsys)
    assert data["event"] == "x"
    assert data["service"] == "svc"
    assert isinstance(data["trace_id"], str) and len(data["trace_id"]) == 32
    int(data["trace_id"], 16)
    assert len(str(data["span_id"])) == 16


def test_log_without_span_has_no_trace_id(capsys):
    configure_logging("svc", "INFO")
    structlog.get_logger().info("x")
    assert "trace_id" not in _last_json(capsys)


def test_log_redacts_secrets(capsys):
    configure_logging("svc", "INFO")
    structlog.get_logger().info(
        "x", password="abc", refresh_token="def", Authorization="Bearer ghi", user="ana"
    )
    out = capsys.readouterr().out
    assert "abc" not in out
    assert "def" not in out
    assert "ghi" not in out
    data = json.loads(out.splitlines()[-1])
    assert data["password"] == "[redacted]"
    assert data["user"] == "ana"


def test_stdlib_logging_goes_through_json_with_trace(capsys):
    configure_logging("svc", "INFO")
    tracer = TracerProvider().get_tracer("t")
    with tracer.start_as_current_span("s"):
        logging.getLogger("ks_platform.health").warning("ready_check failed")
    data = _last_json(capsys)
    assert data["event"] == "ready_check failed"
    assert data["level"] == "warning"
    assert len(str(data["trace_id"])) == 32


def test_log_level_filters(capsys):
    configure_logging("svc", "WARNING")
    structlog.get_logger().info("quiet")
    assert capsys.readouterr().out.strip() == ""


class _Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="KS_TEST_")


def _settings(endpoint: str | None = None) -> _Settings:
    return _Settings(service_name="svc", database_url="x", jwks_url="y", otel_endpoint=endpoint)


@pytest.fixture
def otel_reset():
    """Desfaz o estado global do OTel para que os testes não vazem providers."""
    yield
    HTTPXClientInstrumentor().uninstrument()
    AsyncPGInstrumentor().uninstrument()
    observability._providers = None  # noqa: SLF001
    trace._TRACER_PROVIDER = None  # noqa: SLF001
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # noqa: SLF001
    metrics_internal._METER_PROVIDER = None  # noqa: SLF001
    metrics_internal._METER_PROVIDER_SET_ONCE._done = False  # noqa: SLF001


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "1"}

    return app


def test_providers_without_endpoint_have_no_otlp_and_carry_service_name():
    tracer_provider, meter_provider = build_providers(_settings())
    assert tracer_provider._active_span_processor._span_processors == ()  # noqa: SLF001
    assert meter_provider._metric_readers == []  # noqa: SLF001
    assert tracer_provider.resource.attributes["service.name"] == "svc"
    assert meter_provider._sdk_config.resource.attributes["service.name"] == "svc"  # noqa: SLF001


def test_providers_with_endpoint_configure_otlp_exporters():
    tracer_provider, meter_provider = build_providers(_settings("http://localhost:4317"))
    (processor,) = tracer_provider._active_span_processor._span_processors  # noqa: SLF001
    assert isinstance(getattr(processor, "span_exporter", None), OTLPSpanExporter)
    (reader,) = meter_provider._metric_readers  # noqa: SLF001
    assert isinstance(reader, PeriodicExportingMetricReader)
    assert isinstance(reader._exporter, OTLPMetricExporter)  # noqa: SLF001
    tracer_provider.shutdown()
    meter_provider.shutdown()


async def test_configure_observability_twice_instruments_both_apps(asgi_client_factory, otel_reset):
    exporter = InMemorySpanExporter()
    app1, app2 = _app(), _app()
    configure_observability(app1, _settings(), span_exporter=exporter)
    configure_observability(app2, _settings())
    for app in (app1, app2):
        exporter.clear()
        async with asgi_client_factory(app) as client:
            assert (await client.get("/ping")).status_code == 200
        servers = [s for s in exporter.get_finished_spans() if s.kind == SpanKind.SERVER]
        assert servers, "no server span"
        assert servers[0].resource.attributes["service.name"] == "svc"
