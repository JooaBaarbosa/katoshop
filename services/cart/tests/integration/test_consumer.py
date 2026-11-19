import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from typing import Any

import aio_pika
import httpx
import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from structlog.testing import capture_logs

from cart.adapters.consumer import (
    BINDINGS,
    EXCHANGE,
    PRICE_CHANGED,
    PRODUCT_ARCHIVED,
    QUEUE,
    STOCK_CHANGED,
    handle_catalog_event,
)
from cart.adapters.redis_repo import RedisCartRepository
from cart.domain.cart import Cart, CartItem, Notice, add_item
from cart.main import create_app
from cart.settings import CartSettings
from ks_platform.events import Envelope, new_event
from ks_platform.messaging import AmqpPublisher, declare_consumer_topology

GUEST_TTL = 3600
LIMITS = {"max_lines": 50, "max_qty": 20}


@pytest.fixture
async def redis(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def repo(redis: Redis) -> RedisCartRepository:
    return RedisCartRepository(redis, guest_ttl_s=GUEST_TTL)


def make_item(variant_id: str, **overrides: Any) -> CartItem:
    item = CartItem(
        variant_id=variant_id,
        product_id=str(uuid.uuid7()),
        product_slug="camiseta-basica",
        name="Camiseta básica",
        color_code="preto",
        color_name="Preto",
        size_code="M",
        image_url=None,
        unit_price_cents=4990,
        available=10,
        category_slug="camisetas",
        collection_slugs=[],
        quantity=2,
        price_version=1,
        stock_version=1,
    )
    return replace(item, **overrides)


def put(*items: CartItem) -> Callable[[Cart], None]:
    def fn(cart: Cart) -> None:
        for item in items:
            cart.items[item.variant_id] = replace(item)

    return fn


async def guest_with(repo: RedisCartRepository, *items: CartItem) -> str:
    cart = await repo.new_guest()
    await repo.mutate(cart.cart_id, put(*items))
    return cart.cart_id


async def user_with(repo: RedisCartRepository, *items: CartItem) -> str:
    cart = await repo.cart_for_user(str(uuid.uuid7()))
    await repo.mutate(cart.cart_id, put(*items))
    return cart.cart_id


async def line(repo: RedisCartRepository, cart_id: str, variant_id: str) -> CartItem:
    cart = await repo.get(cart_id)
    assert cart is not None
    return cart.items[variant_id]


def price_event(variant_id: str, new: int, version: int, old: int = 4990) -> Envelope:
    return new_event(
        PRICE_CHANGED,
        "catalog",
        {
            "variant_id": variant_id,
            "sku": "CAM-PRETO-M",
            "product_id": str(uuid.uuid7()),
            "old_price_cents": old,
            "new_price_cents": new,
            "version": version,
        },
    )


def stock_event(variant_id: str, available: int, version: int) -> Envelope:
    return new_event(
        STOCK_CHANGED,
        "catalog",
        {
            "variant_id": variant_id,
            "sku": "CAM-PRETO-M",
            "available": available,
            "version": version,
        },
    )


def archived_event(*variant_ids: str) -> Envelope:
    return new_event(
        PRODUCT_ARCHIVED,
        "catalog",
        {"product_id": str(uuid.uuid7()), "variant_ids": list(variant_ids)},
    )


def vid() -> str:
    return str(uuid.uuid7())


async def test_price_event_updates_all_carts_with_notice(repo: RedisCartRepository) -> None:
    v = vid()
    guest = await guest_with(repo, make_item(v))
    user = await user_with(repo, make_item(v), make_item(other := vid()))
    event = price_event(v.upper(), 5990, 2)  # variant_id não canônico vindo do produtor

    await handle_catalog_event(event, repo)

    for cart_id in (guest, user):
        item = await line(repo, cart_id, v)
        assert item.unit_price_cents == 5990
        assert item.variant_version == 2
        assert item.notice == Notice("price_changed", old_price_cents=4990, new_price_cents=5990)
    assert (await line(repo, user, other)).unit_price_cents == 4990
    assert await repo.processed(str(event.id))


async def test_duplicate_event_applied_once(repo: RedisCartRepository) -> None:
    # O arquivamento não tem versão: só a deduplicação por id impede a reaplicação.
    v = vid()
    cart_id = await guest_with(repo, make_item(v))
    event = archived_event(v)
    await handle_catalog_event(event, repo)
    assert (await line(repo, cart_id, v)).archived is True

    # O produto volta a ficar ativo e o cliente adiciona de novo (snapshot novo e ativo).
    def readd(cart: Cart) -> None:
        add_item(cart, make_item(v, price_version=3, stock_version=3, quantity=0), 1, **LIMITS)

    await repo.mutate(cart_id, readd)
    await handle_catalog_event(event, repo)  # reentrega do mesmo evento

    item = await line(repo, cart_id, v)
    assert item.archived is False
    assert item.unavailable is False


async def test_stale_version_ignored(repo: RedisCartRepository) -> None:
    v = vid()
    cart_id = await guest_with(repo, make_item(v, price_version=5, stock_version=5))
    before = await repo.get(cart_id)
    assert before is not None

    await handle_catalog_event(price_event(v, 9990, 4), repo)
    await handle_catalog_event(stock_event(v, 0, 5), repo)

    after = await repo.get(cart_id)
    assert after is not None
    assert after == before  # nada gravado, nem a versão do carrinho


@pytest.mark.parametrize("stock_first", [True, False])
async def test_price_and_stock_events_apply_in_either_order(
    repo: RedisCartRepository, stock_first: bool
) -> None:
    # S11: o catalog usa uma versão só para os dois tipos; a fila pode inverter a ordem.
    v = vid()
    cart_id = await guest_with(repo, make_item(v, quantity=5))
    events = [price_event(v, 5990, 2), stock_event(v, 3, 3)]
    for event in reversed(events) if stock_first else events:
        await handle_catalog_event(event, repo)

    item = await line(repo, cart_id, v)
    assert (item.unit_price_cents, item.available, item.quantity) == (5990, 3, 3)
    assert (item.price_version, item.stock_version) == (2, 3)


async def test_archived_marks_unavailable(repo: RedisCartRepository) -> None:
    v1, v2, kept = vid(), vid(), vid()
    one = await guest_with(repo, make_item(v1), make_item(v2), make_item(kept))
    two = await user_with(repo, make_item(v2))

    await handle_catalog_event(archived_event(v1, v2), repo)

    for cart_id, variant_id in ((one, v1), (one, v2), (two, v2)):
        item = await line(repo, cart_id, variant_id)
        assert item.archived is True
        assert item.unavailable is True
        assert item.notice == Notice("unavailable")
    assert (await line(repo, one, kept)).unavailable is False
    cart = await repo.get(one)
    assert cart is not None
    assert cart.version == 2  # uma transação para as duas linhas do mesmo carrinho


async def test_event_for_expired_cart_cleans_index(repo: RedisCartRepository, redis: Redis) -> None:
    # Review Focus 2: o TTL apagou o carrinho de visitante, mas o índice reverso ficou.
    v = vid()
    expired = await guest_with(repo, make_item(v))
    alive = await guest_with(repo, make_item(v))
    await redis.delete(f"cart:{expired}", f"cart:{expired}:items")
    event = price_event(v, 5990, 2)

    await handle_catalog_event(event, repo)

    assert await repo.carts_for_variant(v) == {alive}
    assert (await line(repo, alive, v)).unit_price_cents == 5990
    assert await repo.processed(str(event.id))


async def test_event_does_not_renew_guest_ttl(repo: RedisCartRepository, redis: Redis) -> None:
    v = vid()
    cart_id = await guest_with(repo, make_item(v))
    await redis.expire(f"cart:{cart_id}", 100)
    await redis.expire(f"cart:{cart_id}:items", 100)

    await handle_catalog_event(price_event(v, 5990, 2), repo)

    assert (await line(repo, cart_id, v)).unit_price_cents == 5990
    assert 0 < await redis.ttl(f"cart:{cart_id}") <= 100
    assert 0 < await redis.ttl(f"cart:{cart_id}:items") <= 100


async def test_cart_without_the_line_stays_in_index(
    repo: RedisCartRepository, redis: Redis
) -> None:
    # Carrinho existe mas sem a linha (ex.: corrida com um add): não sai do índice.
    v = vid()
    cart_id = await guest_with(repo, make_item(vid()))
    await redis.sadd(f"variant:{v}:carts", cart_id)
    before = await repo.get(cart_id)

    await handle_catalog_event(price_event(v, 5990, 2), repo)

    assert await repo.carts_for_variant(v) == {cart_id}
    assert await repo.get(cart_id) == before


async def test_stock_changed_after_archived_keeps_unavailable(repo: RedisCartRepository) -> None:
    v = vid()
    cart_id = await guest_with(repo, make_item(v))

    await handle_catalog_event(archived_event(v), repo)
    await handle_catalog_event(stock_event(v, 7, 2), repo)

    item = await line(repo, cart_id, v)
    assert item.archived is True
    assert item.unavailable is True
    assert item.available == 7
    assert item.notice == Notice("unavailable")


async def test_stock_event_reduces_quantity_or_marks_unavailable(
    repo: RedisCartRepository,
) -> None:
    v1, v2 = vid(), vid()
    cart_id = await guest_with(repo, make_item(v1, quantity=5), make_item(v2))

    await handle_catalog_event(stock_event(v1, 3, 2), repo)
    await handle_catalog_event(stock_event(v2, 0, 2), repo)

    reduced = await line(repo, cart_id, v1)
    assert reduced.quantity == 3
    assert reduced.notice == Notice("quantity_reduced", quantity=3)
    assert (await line(repo, cart_id, v2)).notice == Notice("unavailable")


async def test_applied_event_is_logged_with_cart_count(
    repo: RedisCartRepository, redis: Redis
) -> None:
    v = vid()
    await guest_with(repo, make_item(v))
    await guest_with(repo, make_item(v))
    # carrinho expirado ainda no índice: não conta como atualizado
    expired = await guest_with(repo, make_item(v))
    await redis.delete(f"cart:{expired}", f"cart:{expired}:items")
    event = stock_event(v, 7, 2)

    with capture_logs() as logs:
        await handle_catalog_event(event, repo)
        await handle_catalog_event(event, repo)  # duplicado: já processado, não loga de novo

    applied = [entry for entry in logs if entry["event"] == "catalog_event.applied"]
    assert applied == [
        {
            "event": "catalog_event.applied",
            "log_level": "info",
            "event_id": str(event.id),
            "type": STOCK_CHANGED,
            "carts": 2,
        }
    ]


@pytest.mark.parametrize(
    ("event_type", "data"),
    [
        (PRICE_CHANGED, {"variant_id": "nao-e-uuid", "new_price_cents": 1, "version": 2}),
        (PRICE_CHANGED, {"variant_id": str(uuid.uuid7()), "version": 2}),
        (PRICE_CHANGED, {"variant_id": str(uuid.uuid7()), "new_price_cents": "10", "version": 2}),
        (PRICE_CHANGED, {"variant_id": str(uuid.uuid7()), "new_price_cents": -1, "version": 2}),
        (STOCK_CHANGED, {"variant_id": str(uuid.uuid7()), "available": 1, "version": True}),
        (STOCK_CHANGED, {"variant_id": 42, "available": 1, "version": 2}),
        (PRODUCT_ARCHIVED, {"product_id": str(uuid.uuid7()), "variant_ids": "x"}),
        (PRODUCT_ARCHIVED, {"product_id": str(uuid.uuid7()), "variant_ids": [None]}),
    ],
)
async def test_malformed_payload_is_marked_processed(
    repo: RedisCartRepository, event_type: str, data: dict[str, Any]
) -> None:
    event = new_event(event_type, "catalog", data)

    await handle_catalog_event(event, repo)  # não levanta: não vai para retry nem DLQ

    assert await repo.processed(str(event.id))


async def test_unknown_event_type_is_marked_processed(repo: RedisCartRepository) -> None:
    event = new_event("catalog.variant.renamed.v1", "catalog", {"variant_id": vid()})

    await handle_catalog_event(event, repo)

    assert await repo.processed(str(event.id))


async def test_redis_failure_raises_and_is_not_marked(repo: RedisCartRepository) -> None:
    v = vid()
    await guest_with(repo, make_item(v))

    class Failing(RedisCartRepository):
        async def mutate(self, *args: Any, **kwargs: Any) -> Any:
            raise RedisConnectionError("redis fora")

    failing = Failing(repo._redis, guest_ttl_s=GUEST_TTL)  # pyright: ignore[reportPrivateUsage]
    event = price_event(v, 5990, 2)

    with pytest.raises(RedisConnectionError):
        await handle_catalog_event(event, failing)

    assert not await repo.processed(str(event.id))


async def _until(probe: Callable[[], Any], timeout_s: float = 15.0) -> None:
    async with asyncio.timeout(timeout_s):
        while True:
            if await probe():
                return
            await asyncio.sleep(0.1)


async def test_lifespan_consumer_applies_events_from_broker(
    redis_url: str,
    rabbitmq_url: str,
    repo: RedisCartRepository,
    asgi_client_factory: Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    v1, v2 = vid(), vid()
    cart_id = await guest_with(repo, make_item(v1), make_item(v2))
    settings = CartSettings(
        redis_url=redis_url,
        amqp_url=rabbitmq_url,
        client_secret="x",  # noqa: S106
    )
    connection = await aio_pika.connect(rabbitmq_url)
    publisher = AmqpPublisher(rabbitmq_url, EXCHANGE)
    try:
        # A fila é durável: declará-la antes garante que nada se perde enquanto o consumidor sobe.
        await declare_consumer_topology(
            await connection.channel(), exchange=EXCHANGE, queue=QUEUE, bindings=BINDINGS
        )
        async with asgi_client_factory(create_app(settings)) as http_client:
            await publisher.publish(price_event(v1, 5990, 2), PRICE_CHANGED)
            await publisher.publish(archived_event(v2), PRODUCT_ARCHIVED)

            async def applied() -> bool:
                cart = await repo.get(cart_id)
                assert cart is not None
                return cart.items[v1].unit_price_cents == 5990 and cart.items[v2].archived

            await _until(applied)
            assert (await http_client.get("/health/ready")).status_code == 200
    finally:
        await publisher.close()
        await connection.close()


async def test_broker_down_does_not_block_startup(
    redis_url: str,
    asgi_client_factory: Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    settings = CartSettings(
        redis_url=redis_url,
        amqp_url="amqp://guest:guest@127.0.0.1:1/",
        client_secret="x",  # noqa: S106
    )
    async with asgi_client_factory(create_app(settings)) as http_client:
        assert (await http_client.get("/health/ready")).status_code == 200
