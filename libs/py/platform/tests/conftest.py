from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from opentelemetry import metrics, trace
from opentelemetry.metrics import _internal as metrics_internal
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

pytest_plugins = ["ks_platform.testing"]


@dataclass
class OtelCapture:
    spans: InMemorySpanExporter
    metrics: InMemoryMetricReader


@pytest.fixture
def otel_capture() -> Iterator[OtelCapture]:
    """Providers OTel globais em memória; desfaz o estado global no fim do teste."""
    spans = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
    yield OtelCapture(spans, reader)
    trace._TRACER_PROVIDER = None  # noqa: SLF001
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # noqa: SLF001
    metrics_internal._METER_PROVIDER = None  # noqa: SLF001
    metrics_internal._METER_PROVIDER_SET_ONCE._done = False  # noqa: SLF001
