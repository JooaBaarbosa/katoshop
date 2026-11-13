"""Publicação e consumo AMQP (RabbitMQ) com confirms, retry por fila de espera e DLQ."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

import aio_pika
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
    HeadersType,
)
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import SpanKind, StatusCode

from ks_platform.events import Envelope

logger = logging.getLogger("ks_platform.messaging")

ATTEMPT_HEADER = "x-attempt"
ERROR_HEADER = "x-error"
_CONTENT_TYPE = "application/json"
_PREFETCH = 10
_MAX_ERROR_LEN = 500

type Handler = Callable[[Envelope], Awaitable[None]]


class EventPublisher(Protocol):
    async def publish(self, event: Envelope, routing_key: str) -> None:
        """Só retorna depois do confirm do broker."""
        ...


def retry_queue_name(queue: str, delay_s: int) -> str:
    return f"{queue}.retry.{delay_s}s"


def dlq_name(queue: str) -> str:
    return f"{queue}.dlq"


class AmqpPublisher(EventPublisher):
    """Publica no exchange topic com publisher confirms e mensagem persistente.

    Conecta sob demanda no primeiro `publish` se `connect()` não foi chamado (ou falhou),
    para o relay da outbox seguir tentando enquanto o broker estiver fora.
    """

    def __init__(self, url: str, exchange: str, *, publish_timeout_s: float = 5.0) -> None:
        self._url = url
        self._exchange_name = exchange
        self._timeout = publish_timeout_s
        self._connection: AbstractRobustConnection | None = None
        self._exchange: AbstractExchange | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        async with self._lock:
            if self._exchange is not None:
                return
            connection = await aio_pika.connect_robust(self._url, timeout=self._timeout)
            try:
                channel = await connection.channel(publisher_confirms=True)
                self._exchange = await channel.declare_exchange(
                    self._exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
                )
            except BaseException:
                await connection.close()
                raise
            self._connection = connection

    async def close(self) -> None:
        async with self._lock:
            if self._connection is not None:
                await self._connection.close()
            self._connection = None
            self._exchange = None

    async def publish(self, event: Envelope, routing_key: str) -> None:
        if self._exchange is None:
            await self.connect()
        assert self._exchange is not None  # noqa: S101 - garantido por connect()
        headers: dict[str, str] = {}
        inject(headers)
        message = aio_pika.Message(
            event.to_json(),
            headers=dict(headers),
            content_type=_CONTENT_TYPE,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=str(event.id),
            type=event.type,
            timestamp=event.occurred_at,
        )
        # mandatory=False: sem fila ligada o evento é descartado pelo broker (semântica topic).
        await self._exchange.publish(message, routing_key, mandatory=False, timeout=self._timeout)


async def declare_consumer_topology(
    channel: AbstractChannel,
    *,
    exchange: str,
    queue: str,
    bindings: list[str],
    retry_delays_s: tuple[int, ...] = (1, 5, 25),
) -> None:
    """Exchange topic, fila principal, filas de espera com TTL (voltam à principal) e DLQ."""
    ex = await channel.declare_exchange(exchange, aio_pika.ExchangeType.TOPIC, durable=True)
    main = await channel.declare_queue(queue, durable=True)
    for key in bindings:
        await main.bind(ex, key)
    for delay in dict.fromkeys(retry_delays_s):
        await channel.declare_queue(
            retry_queue_name(queue, delay),
            durable=True,
            arguments={
                "x-message-ttl": delay * 1000,
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": queue,
            },
        )
    await channel.declare_queue(dlq_name(queue), durable=True)


def _carrier(headers: Mapping[str, object]) -> dict[str, str]:
    carrier: dict[str, str] = {}
    for key, value in headers.items():
        if isinstance(value, bytes):
            value = value.decode(errors="replace")
        if isinstance(value, str):
            carrier[key] = value
    return carrier


def _attempt(headers: Mapping[str, object]) -> int:
    value = headers.get(ATTEMPT_HEADER, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


class EventConsumer:
    """Consome a fila; o handler roda num span filho do `traceparent` recebido.

    Sucesso → ack. Exceção → republica na fila de espera da tentativa (`x-attempt` + 1) e ack;
    esgotadas as esperas, vai para a DLQ. Envelope inválido vai direto para a DLQ.
    Não trata idempotência: isso fica com o handler.
    """

    def __init__(
        self,
        url: str,
        *,
        exchange: str,
        queue: str,
        bindings: list[str],
        handler: Handler,
        retry_delays_s: tuple[int, ...] = (1, 5, 25),
    ) -> None:
        self._url = url
        self._exchange = exchange
        self._queue_name = queue
        self._bindings = bindings
        self._handler = handler
        self._delays = retry_delays_s
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._queue: AbstractQueue | None = None
        self._consumer_tag: str | None = None

    async def start(self) -> None:
        connection = await aio_pika.connect_robust(self._url)
        try:
            channel = await connection.channel(publisher_confirms=True)
            await channel.set_qos(prefetch_count=_PREFETCH)
            await declare_consumer_topology(
                channel,
                exchange=self._exchange,
                queue=self._queue_name,
                bindings=self._bindings,
                retry_delays_s=self._delays,
            )
            queue = await channel.get_queue(self._queue_name, ensure=False)
            self._consumer_tag = await queue.consume(self._on_message)
        except BaseException:
            await connection.close()
            raise
        self._connection, self._channel, self._queue = connection, channel, queue

    async def stop(self) -> None:
        if self._queue is not None and self._consumer_tag is not None:
            await self._queue.cancel(self._consumer_tag)
        if self._connection is not None:
            await self._connection.close()
        self._connection = self._channel = self._queue = None
        self._consumer_tag = None

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        headers = dict(message.headers or {})
        attempt = _attempt(headers)
        try:
            event = Envelope.from_json(message.body)
        except ValueError as exc:
            logger.warning("mensagem com envelope inválido em %s: %s", self._queue_name, exc)
            await self._forward(message, dlq_name(self._queue_name), headers, exc)
            return
        error = await self._handle(event, headers, attempt)
        if error is None:
            await message.ack()
            return
        if attempt < len(self._delays):
            target = retry_queue_name(self._queue_name, self._delays[attempt])
            headers[ATTEMPT_HEADER] = attempt + 1
        else:
            target = dlq_name(self._queue_name)
            logger.warning(
                "evento %s (%s) esgotou as tentativas; enviado para a DLQ", event.id, event.type
            )
        await self._forward(message, target, headers, error)

    async def _handle(
        self, event: Envelope, headers: Mapping[str, object], attempt: int
    ) -> Exception | None:
        tracer = trace.get_tracer("ks_platform.messaging")
        with tracer.start_as_current_span(
            f"{self._queue_name} process",
            context=extract(_carrier(headers)),
            kind=SpanKind.CONSUMER,
            attributes={
                "messaging.system": "rabbitmq",
                "messaging.operation.type": "process",
                "messaging.destination.name": self._queue_name,
                "messaging.message.id": str(event.id),
                "messaging.rabbitmq.destination.routing_key": event.type,
                "ks.event.attempt": attempt,
            },
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                await self._handler(event)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(StatusCode.ERROR, type(exc).__name__)
                logger.warning(
                    "handler falhou para o evento %s (%s), tentativa %d",
                    event.id,
                    event.type,
                    attempt,
                    exc_info=True,
                )
                return exc
        return None

    async def _forward(
        self,
        message: AbstractIncomingMessage,
        routing_key: str,
        headers: HeadersType,
        error: Exception,
    ) -> None:
        """Republica (com confirm) pelo exchange padrão e só então dá ack na original."""
        assert self._channel is not None  # noqa: S101 - consumidor iniciado
        headers[ERROR_HEADER] = f"{type(error).__name__}: {error}"[:_MAX_ERROR_LEN]
        try:
            await self._channel.default_exchange.publish(
                aio_pika.Message(
                    message.body,
                    headers=headers,
                    content_type=message.content_type,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    message_id=message.message_id,
                    type=message.type,
                    timestamp=message.timestamp,
                ),
                routing_key=routing_key,
            )
        except Exception:
            logger.exception("falha ao encaminhar mensagem para %s; devolvendo à fila", routing_key)
            await message.nack(requeue=True)
            return
        await message.ack()
