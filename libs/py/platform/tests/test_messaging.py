import asyncio
import json
import uuid
from collections.abc import AsyncIterator

import aio_pika
import pytest
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage
from opentelemetry import trace

from ks_platform.events import Envelope, new_event
from ks_platform.messaging import (
    AmqpPublisher,
    EventConsumer,
    EventPublisher,
    declare_consumer_topology,
)


@pytest.fixture
def names() -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return f"test.events.{suffix}", f"test.consumer.{suffix}"


@pytest.fixture
async def channel(rabbitmq_url) -> AsyncIterator[AbstractChannel]:
    connection = await aio_pika.connect(rabbitmq_url)
    try:
        yield await connection.channel()
    finally:
        await connection.close()


@pytest.fixture
async def publisher(rabbitmq_url, names) -> AsyncIterator[AmqpPublisher]:
    exchange, _ = names
    pub = AmqpPublisher(rabbitmq_url, exchange)
    await pub.connect()
    try:
        yield pub
    finally:
        await pub.close()


async def _get(channel: AbstractChannel, queue: str, timeout_s: float) -> AbstractIncomingMessage:
    q = await channel.get_queue(queue, ensure=True)
    async with asyncio.timeout(timeout_s):
        while True:
            message = await q.get(no_ack=True, fail=False)
            if message is not None:
                return message
            await asyncio.sleep(0.05)


def test_amqp_publisher_satisfies_protocol():
    publisher: EventPublisher = AmqpPublisher("amqp://x", "ex")
    assert publisher is not None


async def test_declare_consumer_topology_creates_retry_queues_and_dlq(channel, names):
    exchange, queue = names
    await declare_consumer_topology(
        channel, exchange=exchange, queue=queue, bindings=["a.*.v1"], retry_delays_s=(1, 5)
    )
    for name in (queue, f"{queue}.retry.1s", f"{queue}.retry.5s", f"{queue}.dlq"):
        await channel.get_queue(name, ensure=True)
    # Redeclarar com os mesmos argumentos é idempotente.
    await declare_consumer_topology(
        channel, exchange=exchange, queue=queue, bindings=["a.*.v1"], retry_delays_s=(1, 5)
    )


async def test_retry_queue_dead_letters_back_to_main_queue(channel, names):
    exchange, queue = names
    await declare_consumer_topology(
        channel, exchange=exchange, queue=queue, bindings=[], retry_delays_s=(1,)
    )
    await channel.default_exchange.publish(aio_pika.Message(b"x"), routing_key=f"{queue}.retry.1s")
    message = await _get(channel, queue, timeout_s=10)
    assert message.body == b"x"


async def test_publisher_sends_persistent_json_with_traceparent(
    channel, names, publisher, otel_capture
):
    exchange, queue = names
    await declare_consumer_topology(channel, exchange=exchange, queue=queue, bindings=["a.#"])
    event = new_event("a.b.v1", "test", {"k": 1})
    with trace.get_tracer("test").start_as_current_span("produce") as span:
        await publisher.publish(event, "a.b.v1")
        trace_id = span.get_span_context().trace_id

    message = await _get(channel, queue, timeout_s=5)

    assert Envelope.from_json(message.body) == event
    assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert message.content_type == "application/json"
    assert message.message_id == str(event.id)
    traceparent = message.headers["traceparent"]
    assert isinstance(traceparent, str)
    assert traceparent.split("-")[1] == format(trace_id, "032x")


async def test_publish_connects_lazily(rabbitmq_url, channel, names):
    exchange, queue = names
    await declare_consumer_topology(channel, exchange=exchange, queue=queue, bindings=["#"])
    pub = AmqpPublisher(rabbitmq_url, exchange)
    try:
        await pub.publish(new_event("a.b.v1", "test", {}), "a.b.v1")
    finally:
        await pub.close()
    assert (await _get(channel, queue, timeout_s=5)).body


async def test_publish_to_unreachable_broker_raises():
    pub = AmqpPublisher("amqp://guest:guest@127.0.0.1:1/", "ex")
    with pytest.raises(OSError):
        await pub.publish(new_event("a.b.v1", "test", {}), "a.b.v1")
    await pub.close()


async def test_publish_consume_roundtrip_with_traceparent(
    rabbitmq_url, names, publisher, otel_capture
):
    exchange, queue = names
    received: list[tuple[Envelope, int, int]] = []
    done = asyncio.Event()

    async def handler(event: Envelope) -> None:
        ctx = trace.get_current_span().get_span_context()
        received.append((event, ctx.trace_id, ctx.span_id))
        done.set()

    consumer = EventConsumer(
        rabbitmq_url, exchange=exchange, queue=queue, bindings=["a.*.v1"], handler=handler
    )
    await consumer.start()
    try:
        event = new_event("a.b.v1", "test", {"k": 1})
        ignored = new_event("z.b.v1", "test", {})
        with trace.get_tracer("test").start_as_current_span("produce") as span:
            await publisher.publish(ignored, ignored.type)
            await publisher.publish(event, event.type)
            producer = span.get_span_context()
        async with asyncio.timeout(10):
            await done.wait()
    finally:
        await consumer.stop()

    ((got, trace_id, span_id),) = received
    assert got == event
    assert trace_id == producer.trace_id
    assert span_id != producer.span_id
    (consumer_span,) = [
        s for s in otel_capture.spans.get_finished_spans() if s.name == f"{queue} process"
    ]
    assert consumer_span.context.span_id == span_id
    assert consumer_span.attributes is not None
    assert consumer_span.attributes["messaging.message.id"] == str(event.id)


async def test_handler_failure_retries_then_dlq(rabbitmq_url, channel, names, publisher):
    exchange, queue = names
    attempts: list[Envelope] = []

    async def handler(event: Envelope) -> None:
        attempts.append(event)
        raise RuntimeError("falhou")

    consumer = EventConsumer(
        rabbitmq_url,
        exchange=exchange,
        queue=queue,
        bindings=["a.#"],
        handler=handler,
        retry_delays_s=(1, 1, 1),
    )
    await consumer.start()
    try:
        event = new_event("a.b.v1", "test", {})
        await publisher.publish(event, event.type)
        dead = await _get(channel, f"{queue}.dlq", timeout_s=20)
    finally:
        await consumer.stop()

    assert attempts == [event] * 4
    assert Envelope.from_json(dead.body) == event
    assert dead.headers["x-attempt"] == 3
    assert "RuntimeError" in str(dead.headers["x-error"])
    main = await channel.get_queue(queue, ensure=True)
    assert await main.get(no_ack=True, fail=False) is None


async def test_handler_recovers_on_retry(rabbitmq_url, names, publisher):
    exchange, queue = names
    calls = 0
    done = asyncio.Event()

    async def handler(_event: Envelope) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transitório")
        done.set()

    consumer = EventConsumer(
        rabbitmq_url,
        exchange=exchange,
        queue=queue,
        bindings=["a.#"],
        handler=handler,
        retry_delays_s=(1, 1, 1),
    )
    await consumer.start()
    try:
        await publisher.publish(new_event("a.b.v1", "test", {}), "a.b.v1")
        async with asyncio.timeout(10):
            await done.wait()
    finally:
        await consumer.stop()
    assert calls == 2


async def test_invalid_envelope_goes_straight_to_dlq(rabbitmq_url, channel, names):
    exchange, queue = names
    calls: list[Envelope] = []

    async def handler(event: Envelope) -> None:
        calls.append(event)

    consumer = EventConsumer(
        rabbitmq_url,
        exchange=exchange,
        queue=queue,
        bindings=["a.#"],
        handler=handler,
        retry_delays_s=(1, 1, 1),
    )
    await consumer.start()
    try:
        ex = await channel.get_exchange(exchange)
        await ex.publish(aio_pika.Message(b"{quebrado"), routing_key="a.b.v1")
        await ex.publish(
            aio_pika.Message(json.dumps({"type": "a.b.v1"}).encode()), routing_key="a.b.v1"
        )
        first = await _get(channel, f"{queue}.dlq", timeout_s=5)
        second = await _get(channel, f"{queue}.dlq", timeout_s=5)
    finally:
        await consumer.stop()

    assert {first.body, second.body} == {b"{quebrado", b'{"type": "a.b.v1"}'}
    assert calls == []
    retry = await channel.get_queue(f"{queue}.retry.1s", ensure=True)
    assert await retry.get(no_ack=True, fail=False) is None


async def _drop_all_connections(container) -> None:
    def run() -> None:
        code, out = container.exec(["rabbitmqctl", "close_all_connections", "teste de queda"])
        assert code == 0, out

    await asyncio.to_thread(run)


async def _publish_until_ok(pub: AmqpPublisher, event: Envelope, timeout_s: float) -> None:
    async with asyncio.timeout(timeout_s):
        while True:
            try:
                await pub.publish(event, event.type)
                return
            except Exception:  # noqa: BLE001 - reconectando
                await asyncio.sleep(0.5)


async def test_consumer_and_publisher_recover_after_connection_drop(
    rabbitmq_url, rabbitmq_container, names, publisher
):
    exchange, queue = names
    received: list[Envelope] = []
    got = asyncio.Event()

    async def handler(event: Envelope) -> None:
        received.append(event)
        got.set()

    consumer = EventConsumer(
        rabbitmq_url, exchange=exchange, queue=queue, bindings=["a.#"], handler=handler
    )
    await consumer.start()
    try:
        await publisher.publish(new_event("a.b.v1", "test", {}), "a.b.v1")
        async with asyncio.timeout(5):
            await got.wait()
        got.clear()

        await _drop_all_connections(rabbitmq_container)

        after = new_event("a.c.v1", "test", {})
        await _publish_until_ok(publisher, after, timeout_s=30)
        async with asyncio.timeout(30):
            await got.wait()
    finally:
        await consumer.stop()
    assert received[-1] == after


async def test_forward_to_missing_queue_does_not_ack_original(rabbitmq_url, channel, names):
    exchange, queue = names
    consumer = EventConsumer(
        rabbitmq_url,
        exchange=exchange,
        queue=queue,
        bindings=["a.#"],
        handler=_never_called,
        retry_delays_s=(1,),
    )
    await consumer.start()
    try:
        await channel.queue_delete(f"{queue}.dlq")
        ex = await channel.get_exchange(exchange)
        await ex.publish(aio_pika.Message(b"{quebrado"), routing_key="a.b.v1")
        await asyncio.sleep(1.5)
    finally:
        await consumer.stop()
    # Sem ack, a mensagem volta para a fila principal quando o consumidor fecha.
    message = await _get(channel, queue, timeout_s=5)
    assert message.body == b"{quebrado"


async def _never_called(_event: Envelope) -> None:
    raise AssertionError("handler não deveria rodar")


async def test_retry_uses_the_delay_of_each_attempt(
    rabbitmq_url, channel, names, publisher, otel_capture
):
    exchange, queue = names
    loop = asyncio.get_running_loop()
    seen: list[float] = []

    async def handler(_event: Envelope) -> None:
        seen.append(loop.time())
        raise RuntimeError("sempre falha")

    consumer = EventConsumer(
        rabbitmq_url,
        exchange=exchange,
        queue=queue,
        bindings=["a.#"],
        handler=handler,
        retry_delays_s=(1, 2, 3),
    )
    await consumer.start()
    try:
        await publisher.publish(new_event("a.b.v1", "test", {}), "a.b.v1")
        dead = await _get(channel, f"{queue}.dlq", timeout_s=20)
    finally:
        await consumer.stop()

    attempts = [
        s.attributes["ks.event.attempt"]
        for s in otel_capture.spans.get_finished_spans()
        if s.name == f"{queue} process" and s.attributes is not None
    ]
    assert attempts == [0, 1, 2, 3]
    gaps = [later - earlier for earlier, later in zip(seen, seen[1:], strict=False)]
    for gap, delay in zip(gaps, (1, 2, 3), strict=True):
        assert delay - 0.1 <= gap < delay + 0.8, gaps
    assert dead.headers["x-attempt"] == 3
