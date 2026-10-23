import logging
import sys
from collections.abc import Mapping
from typing import Any

import structlog
from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import AsyncEngine
from structlog.typing import EventDict, Processor

from ks_platform.settings import BaseServiceSettings

REDACTED = "[redacted]"
_SECRET_KEYS = frozenset({"password", "token", "refresh_token", "access_token", "authorization"})


def _add_trace_context(_logger: object, _method: str, event_dict: EventDict) -> EventDict:
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def _redact_mapping(data: Mapping[Any, Any]) -> dict[Any, Any]:
    return {
        key: REDACTED
        if str(key).lower() in _SECRET_KEYS
        else (_redact_mapping(value) if isinstance(value, Mapping) else value)
        for key, value in data.items()
    }


def _redact_secrets(_logger: object, _method: str, event_dict: EventDict) -> EventDict:
    return _redact_mapping(event_dict)


def configure_logging(service_name: str, level: str) -> None:
    """JSON no stdout para structlog e para o logging da stdlib, com trace e redação."""

    def add_service(_logger: object, _method: str, event_dict: EventDict) -> EventDict:
        event_dict["service"] = service_name
        return event_dict

    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_service,
        _add_trace_context,
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                _redact_secrets,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())


def configure_observability(
    app: FastAPI, settings: BaseServiceSettings, engine: AsyncEngine | None = None
) -> None:
    """Providers OTel (OTLP gRPC quando `otel_endpoint` existe) e instrumentação."""
    resource = Resource.create({SERVICE_NAME: settings.service_name})
    tracer_provider = TracerProvider(resource=resource)
    readers: list[MetricReader] = []
    if settings.otel_endpoint:
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint))
        )
        readers.append(
            PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=settings.otel_endpoint))
        )
    meter_provider = MeterProvider(resource=resource, metric_readers=readers)
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(meter_provider)

    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=tracer_provider, meter_provider=meter_provider
    )
    HTTPXClientInstrumentor().instrument(
        tracer_provider=tracer_provider, meter_provider=meter_provider
    )
    AsyncPGInstrumentor().instrument(tracer_provider=tracer_provider)
    if engine is not None:
        SQLAlchemyInstrumentor().instrument(
            engine=engine.sync_engine, tracer_provider=tracer_provider
        )
