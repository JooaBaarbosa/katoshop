import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import aio_pika
import pytest
from opentelemetry import trace
from opentelemetry.propagate import inject
from sqlalchemy import MetaData, Table, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ks_platform.db import make_engine, make_session_factory
from ks_platform.events import Envelope, new_event
from ks_platform.messaging import AmqpPublisher
from ks_platform.outbox import OutboxRelay, add_event, outbox_table


class FakePublisher:
    def __init__(self, *, fail_on: set[int] | None = None, delay_s: float = 0.0) -> None:
        """`fail_on`: números (0-based) das chamadas a `publish` que devem falhar."""
        self.published: list[tuple[Envelope, str]] = []
        self.calls = 0
        self._fail_on = fail_on or set()
        self._delay_s = delay_s
        self.changed = asyncio.Event()

    async def publish(self, event: Envelope, routing_key: str) -> None:
        call = self.calls
        self.calls += 1
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        if call in self._fail_on:
            raise ConnectionError("broker fora do ar")
        self.published.append((event, routing_key))
        self.changed.set()

    async def wait_published(self, count: int) -> None:
        while len(self.published) < count:
            self.changed.clear()
            await self.changed.wait()


type Outbox = tuple[async_sessionmaker[AsyncSession], Table]


@pytest.fixture
async def outbox(postgres_url) -> AsyncIterator[Outbox]:
    metadata = MetaData()
    table = outbox_table(metadata)
    engine = make_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    try:
        yield make_session_factory(engine), table
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
        await engine.dispose()


async def _add(factory: async_sessionmaker[AsyncSession], table: Table, n: int) -> list[Envelope]:
    events = [new_event(f"test.thing.n{i}.v1", "test", {"i": i}) for i in range(n)]
    async with factory() as session, session.begin():
        for event in events:
            await add_event(session, table, event)
    return events


async def _rows(factory: async_sessionmaker[AsyncSession], table: Table) -> list[Any]:
    async with factory() as session:
        result = await session.execute(select(table).order_by(table.c.created_at, table.c.id))
        return list(result.all())


def test_outbox_table_definition():
    table = outbox_table(MetaData())
    assert table.name == "outbox"
    assert set(table.c.keys()) == {
        "id",
        "type",
        "payload",
        "created_at",
        "published_at",
        "attempts",
        "traceparent",
    }
    assert table.c.traceparent.nullable
    assert [c.name for c in table.primary_key.columns] == ["id"]
    assert table.c.published_at.nullable
    (index,) = table.indexes
    assert [c.name for c in index.columns] == ["created_at"]
    assert str(index.dialect_options["postgresql"]["where"]) == "published_at IS NULL"


async def test_add_event_inserts_full_envelope(outbox):
    factory, table = outbox
    (event,) = await _add(factory, table, 1)
    (row,) = await _rows(factory, table)
    assert row.id == event.id
    assert row.type == event.type
    assert Envelope.from_dict(row.payload) == event
    assert row.published_at is None
    assert row.attempts == 0


async def test_add_event_rolled_back_leaves_no_row(outbox):
    factory, table = outbox
    async with factory() as session:
        await session.begin()
        await add_event(session, table, new_event("x.y.v1", "test", {}))
        await session.rollback()
    assert await _rows(factory, table) == []


async def test_relay_publishes_and_marks_published(outbox):
    factory, table = outbox
    events = await _add(factory, table, 3)
    publisher = FakePublisher()
    relay = OutboxRelay(factory, table, publisher)

    assert await relay.run_once() == 3

    assert publisher.published == [(e, e.type) for e in events]
    assert all(row.published_at is not None for row in await _rows(factory, table))
    assert await relay.run_once() == 0
    assert len(publisher.published) == 3


async def test_relay_respects_batch_size(outbox):
    factory, table = outbox
    await _add(factory, table, 5)
    relay = OutboxRelay(factory, table, FakePublisher(), batch_size=2)
    assert [await relay.run_once() for _ in range(4)] == [2, 2, 1, 0]


async def test_relay_keeps_rows_when_publisher_fails_then_publishes(outbox):
    factory, table = outbox
    events = await _add(factory, table, 2)
    publisher = FakePublisher(fail_on={0})
    relay = OutboxRelay(factory, table, publisher)

    assert await relay.run_once() == 0
    rows = await _rows(factory, table)
    assert [row.published_at for row in rows] == [None, None]
    assert [row.attempts for row in rows] == [1, 0]

    assert await relay.run_once() == 2
    assert [e for e, _ in publisher.published] == events
    rows = await _rows(factory, table)
    assert all(row.published_at is not None for row in rows)
    assert rows[0].attempts == 1


async def test_relay_failure_mid_batch_commits_what_was_published(outbox):
    factory, table = outbox
    await _add(factory, table, 3)
    relay = OutboxRelay(factory, table, FakePublisher(fail_on={1}))

    assert await relay.run_once() == 1

    rows = await _rows(factory, table)
    assert [row.published_at is not None for row in rows] == [True, False, False]
    assert [row.attempts for row in rows] == [0, 1, 0]


async def test_relay_skip_locked_two_relays_no_duplicates(outbox):
    factory, table = outbox
    events = await _add(factory, table, 10)
    publisher = FakePublisher(delay_s=0.02)
    first = OutboxRelay(factory, table, publisher, batch_size=5)
    second = OutboxRelay(factory, table, publisher, batch_size=5)

    counts = await asyncio.gather(first.run_once(), second.run_once())

    # Sem SKIP LOCKED o segundo relay esperaria o primeiro e não publicaria nada.
    assert counts == [5, 5]
    ids = [e.id for e, _ in publisher.published]
    assert len(ids) == 10
    assert set(ids) == {e.id for e in events}


async def test_relay_deletes_rows_older_than_retention(outbox):
    factory, table = outbox
    old, recent, pending = await _add(factory, table, 3)
    assert await OutboxRelay(factory, table, FakePublisher()).run_once() == 3
    async with factory() as session, session.begin():
        for event, age in ((old, "8 days"), (recent, "6 days")):
            await session.execute(
                update(table)
                .where(table.c.id == event.id)
                .values(published_at=func.now() - text(f"interval '{age}'"))
            )
        await session.execute(
            update(table).where(table.c.id == pending.id).values(published_at=None)
        )
    relay = OutboxRelay(factory, table, FakePublisher(fail_on={0}), retention=timedelta(days=7))

    await relay.run_once()

    assert {row.id for row in await _rows(factory, table)} == {recent.id, pending.id}


async def test_relay_reports_backlog_gauge(outbox, otel_capture):
    factory, table = outbox
    await _add(factory, table, 3)
    relay = OutboxRelay(factory, table, FakePublisher(), batch_size=1)

    await relay.run_once()

    data = otel_capture.metrics.get_metrics_data()
    assert data is not None
    points = [
        point.value
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for metric in sm.metrics
        if metric.name == "outbox.backlog"
        for point in metric.data.data_points
    ]
    assert points == [2]


async def test_run_forever_publishes_until_stopped(outbox):
    factory, table = outbox
    await _add(factory, table, 2)
    publisher = FakePublisher()
    relay = OutboxRelay(factory, table, publisher, interval_s=0.05)
    stop = asyncio.Event()
    task = asyncio.create_task(relay.run_forever(stop))
    await _add(factory, table, 1)
    async with asyncio.timeout(5):
        await publisher.wait_published(3)
    stop.set()
    async with asyncio.timeout(2):
        await task


async def test_run_forever_keeps_going_after_failures(outbox):
    factory, table = outbox
    await _add(factory, table, 1)
    publisher = FakePublisher(fail_on={0, 1})
    relay = OutboxRelay(factory, table, publisher, interval_s=0.02)
    stop = asyncio.Event()
    task = asyncio.create_task(relay.run_forever(stop))
    async with asyncio.timeout(5):
        await publisher.wait_published(1)
    stop.set()
    await task
    (row,) = await _rows(factory, table)
    assert row.attempts == 2


async def test_retention_cleanup_runs_at_most_once_per_minute(outbox):
    factory, table = outbox
    (event,) = await _add(factory, table, 1)
    relay = OutboxRelay(factory, table, FakePublisher(), retention=timedelta(days=7))
    assert await relay.run_once() == 1
    async with factory() as session, session.begin():
        await session.execute(
            update(table)
            .where(table.c.id == event.id)
            .values(published_at=func.now() - text("interval '8 days'"))
        )

    await relay.run_once()

    assert len(await _rows(factory, table)) == 1


async def test_relay_logs_error_after_ten_attempts(outbox, caplog):
    factory, table = outbox
    await _add(factory, table, 1)
    async with factory() as session, session.begin():
        await session.execute(update(table).values(attempts=9))
    relay = OutboxRelay(factory, table, FakePublisher(fail_on={0}))

    await relay.run_once()

    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert errors and "10" in errors[0].getMessage()


class TraceRecordingPublisher(FakePublisher):
    """Guarda o `traceparent` do contexto corrente no momento de cada publish."""

    def __init__(self) -> None:
        super().__init__()
        self.traceparents: list[str | None] = []

    async def publish(self, event: Envelope, routing_key: str) -> None:
        carrier: dict[str, str] = {}
        inject(carrier)
        self.traceparents.append(carrier.get("traceparent"))
        await super().publish(event, routing_key)


def _trace_id(traceparent: str | None) -> str | None:
    return None if traceparent is None else traceparent.split("-")[1]


async def test_add_event_stores_traceparent_of_current_span(outbox, otel_capture):
    factory, table = outbox
    with trace.get_tracer("test").start_as_current_span("request") as span:
        await _add(factory, table, 1)
        trace_id = format(span.get_span_context().trace_id, "032x")
    (row,) = await _rows(factory, table)
    assert _trace_id(row.traceparent) == trace_id


async def test_add_event_without_span_stores_null_traceparent(outbox, otel_capture):
    factory, table = outbox
    await _add(factory, table, 1)
    (row,) = await _rows(factory, table)
    assert row.traceparent is None


async def test_relay_publishes_under_the_trace_of_the_originating_request(outbox, otel_capture):
    factory, table = outbox
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("request-a") as span_a:
        await _add(factory, table, 1)
        trace_a = format(span_a.get_span_context().trace_id, "032x")
    await _add(factory, table, 1)
    with tracer.start_as_current_span("request-b") as span_b:
        await _add(factory, table, 1)
        trace_b = format(span_b.get_span_context().trace_id, "032x")
    publisher = TraceRecordingPublisher()
    relay = OutboxRelay(factory, table, publisher)

    with tracer.start_as_current_span("relay") as relay_span:
        assert await relay.run_once() == 3
        relay_trace = format(relay_span.get_span_context().trace_id, "032x")

    # Linha sem traceparent publica no contexto do próprio relay.
    assert [_trace_id(t) for t in publisher.traceparents] == [trace_a, relay_trace, trace_b]


async def test_relay_amqp_header_carries_trace_of_originating_span(
    outbox, otel_capture, rabbitmq_url
):
    factory, table = outbox
    exchange = f"test.outbox.{uuid.uuid4().hex[:8]}"
    connection = await aio_pika.connect(rabbitmq_url)
    publisher = AmqpPublisher(rabbitmq_url, exchange)
    try:
        channel = await connection.channel()
        ex = await channel.declare_exchange(exchange, aio_pika.ExchangeType.TOPIC, durable=True)
        queue = await channel.declare_queue(exclusive=True)
        await queue.bind(ex, "#")
        with trace.get_tracer("test").start_as_current_span("request") as span:
            (event,) = await _add(factory, table, 1)
            trace_id = format(span.get_span_context().trace_id, "032x")

        assert await OutboxRelay(factory, table, publisher).run_once() == 1

        async with asyncio.timeout(10):
            while True:
                message = await queue.get(no_ack=True, fail=False)
                if message is not None:
                    break
                await asyncio.sleep(0.05)
    finally:
        await publisher.close()
        await connection.close()
    assert message.message_id == str(event.id)
    traceparent = message.headers["traceparent"]
    assert isinstance(traceparent, str)
    assert _trace_id(traceparent) == trace_id
