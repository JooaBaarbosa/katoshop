"""Eventos de domínio gravados na outbox na mesma transação da escrita do admin."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import aio_pika
import httpx
import pytest
from aio_pika.abc import AbstractQueue
from fastapi import FastAPI
from sqlalchemy import select
from testcontainers.core.container import DockerContainer

from catalog.adapters.models import outbox
from catalog.application.events import (
    EVENTS_EXCHANGE,
    PRICE_CHANGED,
    PRODUCT_ARCHIVED,
    STOCK_CHANGED,
)
from ks_platform.events import Envelope
from ks_platform.messaging import AmqpPublisher
from ks_platform.outbox import OutboxRelay

type Json = dict[str, Any]
type Factory = Callable[..., Awaitable[Json]]
type DeclareQueue = Callable[[str], Awaitable[AbstractQueue]]


async def _rows(app: FastAPI, event_type: str, key: str, value: str) -> list[Any]:
    """Linhas da outbox do tipo, filtradas por um campo de `data`, em ordem de gravação."""
    async with app.state.session_factory() as session:
        result = await session.execute(
            select(outbox.c.id, outbox.c.payload, outbox.c.published_at, outbox.c.attempts)
            .where(outbox.c.type == event_type, outbox.c.payload["data"][key].astext == value)
            .order_by(outbox.c.created_at, outbox.c.id)
        )
        return list(result.all())


async def _events(app: FastAPI, event_type: str, key: str, value: str) -> list[Envelope]:
    return [Envelope.from_dict(r.payload) for r in await _rows(app, event_type, key, value)]


async def _generate(admin_client: httpx.AsyncClient, product_id: str, sizes: list[str]) -> Json:
    response = await admin_client.post(
        f"/v1/admin/products/{product_id}/variants/generate",
        json={"colors": ["PRT"], "sizes": sizes},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _patch_variant(admin_client: httpx.AsyncClient, variant: Json, **fields: Any) -> Json:
    response = await admin_client.patch(
        f"/v1/admin/variants/{variant['id']}", json={"version": variant["version"], **fields}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_adjust_stock_writes_stock_changed_in_same_tx(
    app: FastAPI, admin_client: httpx.AsyncClient, make_variant: Factory
) -> None:
    variant = await make_variant()
    response = await admin_client.post(
        f"/v1/admin/variants/{variant['id']}/stock-adjustments",
        json={"delta": 5, "reason": "initial"},
    )
    assert response.status_code == 201, response.text
    updated = response.json()["variant"]
    assert updated["version"] == variant["version"] + 1

    rows = await _rows(app, STOCK_CHANGED, "variant_id", variant["id"])
    assert len(rows) == 1
    assert rows[0].published_at is None
    event = Envelope.from_dict(rows[0].payload)
    assert rows[0].id == event.id
    assert event.producer == "catalog"
    assert event.data == {
        "variant_id": variant["id"],
        "sku": variant["sku"],
        "available": 5,
        "version": updated["version"],
    }


async def test_base_price_change_emits_one_event_per_variant_without_own_price(
    app: FastAPI, admin_client: httpx.AsyncClient, make_product: Factory
) -> None:
    product = await make_product(base_price_cents=24900)
    variants = (await _generate(admin_client, product["id"], ["P", "M", "G"]))["variants"]
    own = await _patch_variant(admin_client, variants[0], price_cents=29900)

    current = (await admin_client.get(f"/v1/admin/products/{product['id']}")).json()
    response = await admin_client.patch(
        f"/v1/admin/products/{product['id']}",
        json={"base_price_cents": 15900, "version": current["version"]},
    )
    assert response.status_code == 200, response.text
    after = {v["id"]: v for v in response.json()["variants"]}

    events = [
        e
        for e in await _events(app, PRICE_CHANGED, "product_id", product["id"])
        if e.data["new_price_cents"] == 15900
    ]
    assert sorted(e.data["variant_id"] for e in events) == sorted(v["id"] for v in variants[1:])
    for event in events:
        variant = after[event.data["variant_id"]]
        assert event.data == {
            "variant_id": variant["id"],
            "sku": variant["sku"],
            "product_id": product["id"],
            "old_price_cents": 24900,
            "new_price_cents": 15900,
            "version": variant["version"],
        }
    # Variantes sem preço próprio ganham versão nova; a de preço próprio fica como estava.
    by_id = {v["id"]: v for v in variants}
    for variant_id in (v["id"] for v in variants[1:]):
        assert after[variant_id]["version"] == by_id[variant_id]["version"] + 1
    assert after[own["id"]]["version"] == own["version"]


async def test_variant_price_change_emits_price_changed_with_old_and_new(
    app: FastAPI, admin_client: httpx.AsyncClient, make_variant: Factory
) -> None:
    variant = await make_variant()
    patched = await _patch_variant(admin_client, variant, price_cents=19900)
    back = await _patch_variant(admin_client, patched, price_cents=None)

    events = await _events(app, PRICE_CHANGED, "variant_id", variant["id"])
    assert [(e.data["old_price_cents"], e.data["new_price_cents"]) for e in events] == [
        (24900, 19900),
        (19900, 24900),
    ]
    assert [e.data["version"] for e in events] == [patched["version"], back["version"]]
    assert events[0].data["sku"] == variant["sku"]
    assert events[0].data["product_id"] == variant["product_id"]


async def test_no_price_event_when_effective_price_is_unchanged(
    app: FastAPI,
    admin_client: httpx.AsyncClient,
    make_product: Factory,
) -> None:
    product = await make_product(base_price_cents=24900)
    variant = (await _generate(admin_client, product["id"], ["M"]))["variants"][0]
    # Preço próprio igual ao base: o preço efetivo continua o mesmo.
    same = await _patch_variant(admin_client, variant, price_cents=24900)
    response = await admin_client.patch(
        f"/v1/admin/products/{product['id']}",
        json={"name": "Moletom Renomeado", "base_price_cents": 24900, "version": 1},
    )
    assert response.status_code == 200, response.text

    assert await _events(app, PRICE_CHANGED, "product_id", product["id"]) == []
    assert await _events(app, STOCK_CHANGED, "variant_id", variant["id"]) == []
    assert same["version"] == variant["version"] + 1


async def test_deactivate_variant_emits_stock_changed_zero(
    app: FastAPI, admin_client: httpx.AsyncClient, make_variant: Factory
) -> None:
    variant = await make_variant(stock=4)
    off = await _patch_variant(admin_client, variant, active=False)
    on = await _patch_variant(admin_client, off, active=True)

    events = await _events(app, STOCK_CHANGED, "variant_id", variant["id"])
    # O primeiro é o do ajuste inicial de estoque (make_variant).
    assert [(e.data["available"], e.data["version"]) for e in events[1:]] == [
        (0, off["version"]),
        (4, on["version"]),
    ]
    assert await _events(app, PRICE_CHANGED, "variant_id", variant["id"]) == []


async def test_price_and_active_in_one_patch_get_distinct_versions(
    app: FastAPI, admin_client: httpx.AsyncClient, make_variant: Factory
) -> None:
    """O carrinho descarta evento com version <= a guardada: dois eventos da mesma escrita
    precisam de versões diferentes para nenhum ser descartado."""
    variant = await make_variant()
    patched = await _patch_variant(admin_client, variant, price_cents=19900, active=False)

    price = await _events(app, PRICE_CHANGED, "variant_id", variant["id"])
    stock = await _events(app, STOCK_CHANGED, "variant_id", variant["id"])
    assert len(price) == 1
    assert len(stock) == 1
    assert price[0].data["version"] < stock[0].data["version"] == patched["version"]
    assert stock[0].data["available"] == 0


async def test_archive_emits_product_archived_with_all_variant_ids(
    app: FastAPI, admin_client: httpx.AsyncClient, make_product: Factory
) -> None:
    product = await make_product()
    variants = (await _generate(admin_client, product["id"], ["P", "M"]))["variants"]
    await _patch_variant(admin_client, variants[0], active=False)
    response = await admin_client.post(f"/v1/admin/products/{product['id']}/archive")
    assert response.status_code == 200, response.text

    events = await _events(app, PRODUCT_ARCHIVED, "product_id", product["id"])
    assert len(events) == 1
    assert events[0].data == {
        "product_id": product["id"],
        "variant_ids": [v["id"] for v in variants],
    }


async def test_failed_write_rolls_back_event(
    app: FastAPI, admin_client: httpx.AsyncClient, make_variant: Factory
) -> None:
    variant = await make_variant(stock=2)
    before = await _rows(app, STOCK_CHANGED, "variant_id", variant["id"])
    response = await admin_client.post(
        f"/v1/admin/variants/{variant['id']}/stock-adjustments",
        json={"delta": -3, "reason": "damage"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "catalog.stock.would_go_negative"
    assert await _rows(app, STOCK_CHANGED, "variant_id", variant["id"]) == before


# ---------------------------------------------------------------------------- broker fora


async def _rabbitmqctl(container: DockerContainer, *args: str) -> None:
    code, output = await asyncio.to_thread(container.exec, ["rabbitmqctl", *args])
    assert code == 0, output


@pytest.fixture
async def bound_queue(rabbitmq_url: str) -> AsyncIterator[DeclareQueue]:
    """Declara (sob demanda) uma fila exclusiva ligada ao exchange do catalog."""
    connections: list[aio_pika.abc.AbstractRobustConnection] = []

    async def declare(routing_key: str) -> AbstractQueue:
        connection = await aio_pika.connect_robust(rabbitmq_url)
        connections.append(connection)
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        queue = await channel.declare_queue(exclusive=True)
        await queue.bind(exchange, routing_key)
        return queue

    yield declare
    for connection in connections:
        await connection.close()


async def _receive(queue: AbstractQueue, event_id: uuid.UUID, timeout_s: float = 10.0) -> Envelope:
    """Espera a mensagem com o id do evento (a fila pode receber eventos de outros testes)."""
    async with asyncio.timeout(timeout_s):
        while True:
            message = await queue.get(no_ack=True, fail=False)
            if message is None:
                await asyncio.sleep(0.1)
                continue
            event = Envelope.from_json(message.body)
            if event.id == event_id:
                return event


async def _drain(relay: OutboxRelay) -> int:
    total = 0
    while count := await relay.run_once():
        total += count
    return total


async def test_writes_succeed_while_broker_down_and_relay_catches_up(
    app: FastAPI,
    admin_client: httpx.AsyncClient,
    make_variant: Factory,
    rabbitmq_url: str,
    rabbitmq_container: DockerContainer,
    bound_queue: DeclareQueue,
) -> None:
    """Review Focus 4. O broker cai com `rabbitmqctl stop_app` (o processo e a porta mapeada
    continuam; só o RabbitMQ para de aceitar conexões) e volta com `start_app`. Reiniciar o
    container mudaria a porta publicada no Docker Desktop e invalidaria a URL da sessão."""
    variant = await make_variant()
    publisher = AmqpPublisher(rabbitmq_url, EVENTS_EXCHANGE, publish_timeout_s=2.0)
    relay = OutboxRelay(app.state.session_factory, outbox, publisher)
    try:
        await _rabbitmqctl(rabbitmq_container, "stop_app")
        try:
            response = await admin_client.post(
                f"/v1/admin/variants/{variant['id']}/stock-adjustments",
                json={"delta": 3, "reason": "initial"},
            )
            assert response.status_code == 201, response.text
            assert await relay.run_once() == 0
        finally:
            await _rabbitmqctl(rabbitmq_container, "start_app")
            await _rabbitmqctl(rabbitmq_container, "await_startup")

        # A linha continua pendente. `attempts` não é conferido aqui: o lote para no primeiro
        # erro, que pode ser numa linha pendente de outro teste gravada antes desta.
        [row] = await _rows(app, STOCK_CHANGED, "variant_id", variant["id"])
        assert row.published_at is None

        queue = await bound_queue(STOCK_CHANGED)
        assert await _drain(relay) >= 1
        received = await _receive(queue, row.id)
    finally:
        await publisher.close()

    assert received.data["available"] == 3
    [row] = await _rows(app, STOCK_CHANGED, "variant_id", variant["id"])
    assert row.published_at is not None
