# ruff: noqa: S105, S106
import json
import logging

import structlog
from fastapi import FastAPI
from opentelemetry.sdk.trace import TracerProvider
from pydantic_settings import SettingsConfigDict

from ks_platform.observability import configure_logging, configure_observability
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


async def test_configure_observability_without_endpoint_is_noop_exporter(asgi_client_factory):
    settings = _Settings(service_name="svc", database_url="x", jwks_url="y")
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "1"}

    configure_observability(app, settings)
    async with asgi_client_factory(app) as client:
        response = await client.get("/ping")
    assert response.status_code == 200
