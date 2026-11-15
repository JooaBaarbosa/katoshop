"""Com `amqp_url`, o lifespan do catalog sobe o relay da outbox e o para no shutdown."""

import asyncio
import secrets
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import aio_pika
import httpx
import pytest

from catalog.application.events import EVENTS_EXCHANGE, STOCK_CHANGED
from catalog.settings import CatalogSettings
from ks_platform.events import Envelope


@pytest.fixture
def settings(migrated_url: str, rabbitmq_url: str, tmp_path: Path) -> CatalogSettings:
    return CatalogSettings(
        database_url=migrated_url, media_root=tmp_path / "media", amqp_url=rabbitmq_url
    )


async def test_lifespan_relay_publishes_stock_changed(
    admin_client: httpx.AsyncClient,
    make_variant: Callable[..., Awaitable[dict[str, Any]]],
    rabbitmq_url: str,
) -> None:
    """`admin_client` roda dentro do lifespan do app criado com `amqp_url`."""
    connection = await aio_pika.connect_robust(rabbitmq_url)
    try:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        queue = await channel.declare_queue(exclusive=True)
        await queue.bind(exchange, STOCK_CHANGED)

        variant = await make_variant(stock=2)

        # O relay roda em segundo plano (a cada 1 s); a fila pode ter eventos de outros testes.
        async with asyncio.timeout(15):
            while True:
                message = await queue.get(no_ack=True, fail=False)
                if message is None:
                    await asyncio.sleep(0.1)
                    continue
                event = Envelope.from_json(message.body)
                if event.data.get("variant_id") == variant["id"]:
                    break
    finally:
        await connection.close()

    assert event.type == STOCK_CHANGED
    assert event.data["available"] == 2
    assert event.data["version"] == variant["version"]


async def test_published_event_carries_the_admin_request_trace(
    admin_client: httpx.AsyncClient,
    make_variant: Callable[..., Awaitable[dict[str, Any]]],
    rabbitmq_url: str,
) -> None:
    """O span da requisição continua o `traceparent` recebido; o evento publicado depois pelo
    relay tem de sair nesse mesmo trace (header AMQP) e com `correlation_id` = trace id."""
    variant = await make_variant()
    trace_id = uuid.uuid4().hex
    connection = await aio_pika.connect_robust(rabbitmq_url)
    try:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        queue = await channel.declare_queue(exclusive=True)
        await queue.bind(exchange, STOCK_CHANGED)

        response = await admin_client.post(
            f"/v1/admin/variants/{variant['id']}/stock-adjustments",
            json={"delta": 1, "reason": "initial"},
            headers={"traceparent": f"00-{trace_id}-{secrets.token_hex(8)}-01"},
        )
        assert response.status_code == 201, response.text

        async with asyncio.timeout(15):
            while True:
                message = await queue.get(no_ack=True, fail=False)
                if message is None:
                    await asyncio.sleep(0.1)
                    continue
                event = Envelope.from_json(message.body)
                if event.data.get("variant_id") == variant["id"]:
                    break
    finally:
        await connection.close()

    assert event.correlation_id == trace_id
    traceparent = message.headers["traceparent"]
    assert isinstance(traceparent, str)
    assert traceparent.split("-")[1] == trace_id
