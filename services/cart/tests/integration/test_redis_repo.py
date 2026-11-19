import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace

import pytest
from redis.asyncio import Redis
from redis.asyncio.client import Pipeline
from redis.exceptions import WatchError

from cart.adapters import redis_repo
from cart.adapters.redis_repo import RedisCartRepository, item_from_json, item_to_json
from cart.domain.cart import Cart, CartError, CartItem, Notice, add_item

GUEST_TTL = 3600


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


def make_item(variant_id: str | None = None, **overrides: object) -> CartItem:
    item = CartItem(
        variant_id=variant_id or str(uuid.uuid4()),
        product_id=str(uuid.uuid4()),
        product_slug="camiseta-basica",
        name="Camiseta básica",
        color_code="preto",
        color_name="Preto",
        size_code="M",
        image_url="/media/camiseta.jpg",
        unit_price_cents=4990,
        available=10,
        category_slug="camisetas",
        collection_slugs=["verao"],
        quantity=1,
        variant_version=1,
    )
    return replace(item, **overrides)  # pyright: ignore[reportArgumentType]


def put(item: CartItem):  # noqa: ANN201
    def fn(cart: Cart) -> None:
        cart.items[item.variant_id] = item

    return fn


async def test_mutate_increments_version_and_indexes_variant(repo: RedisCartRepository) -> None:
    cart = await repo.new_guest()
    item = make_item()

    await repo.mutate(cart.cart_id, put(item))

    stored = await repo.get(cart.cart_id)
    assert stored is not None
    assert stored.version == cart.version + 1
    assert stored.items == {item.variant_id: item}
    assert await repo.carts_for_variant(item.variant_id) == {cart.cart_id}


async def test_mutate_returns_fn_result(repo: RedisCartRepository) -> None:
    cart = await repo.new_guest()

    def fn(c: Cart) -> str:
        c.coupon_code = "BEMVINDO10"
        return "ok"

    assert await repo.mutate(cart.cart_id, fn) == "ok"
    stored = await repo.get(cart.cart_id)
    assert stored is not None
    assert stored.coupon_code == "BEMVINDO10"


async def test_guest_ttl_set_and_renewed(repo: RedisCartRepository, redis: Redis) -> None:
    cart = await repo.new_guest()
    header = f"cart:{cart.cart_id}"
    assert 0 < await redis.ttl(header) <= GUEST_TTL

    await redis.expire(header, 10)
    await repo.mutate(cart.cart_id, put(make_item()))

    assert await redis.ttl(header) > 10
    assert 0 < await redis.ttl(f"cart:{cart.cart_id}:items") <= GUEST_TTL


async def test_user_cart_has_no_ttl(repo: RedisCartRepository, redis: Redis) -> None:
    user_id = str(uuid.uuid4())
    cart = await repo.cart_for_user(user_id)
    await repo.mutate(cart.cart_id, put(make_item()))

    assert cart.owner == f"user:{user_id}"
    assert await redis.ttl(f"cart:{cart.cart_id}") == -1
    assert await redis.ttl(f"cart:{cart.cart_id}:items") == -1
    assert await redis.ttl(f"user:{user_id}:cart") == -1
    again = await repo.cart_for_user(user_id)
    assert again.cart_id == cart.cart_id
    assert len(again.items) == 1


async def test_cart_for_user_concurrent_calls_return_same_cart(
    repo: RedisCartRepository, redis: Redis
) -> None:
    user_id = str(uuid.uuid4())

    carts = await asyncio.gather(*(repo.cart_for_user(user_id) for _ in range(10)))

    assert len({c.cart_id for c in carts}) == 1
    assert len(await redis.keys("cart:*")) == 1


async def test_remove_item_updates_reverse_index(repo: RedisCartRepository) -> None:
    cart = await repo.new_guest()
    keep, gone = make_item(), make_item()
    await repo.mutate(cart.cart_id, put(keep))
    await repo.mutate(cart.cart_id, put(gone))

    await repo.mutate(cart.cart_id, lambda c: c.items.pop(gone.variant_id))

    assert await repo.carts_for_variant(gone.variant_id) == set()
    assert await repo.carts_for_variant(keep.variant_id) == {cart.cart_id}
    stored = await repo.get(cart.cart_id)
    assert stored is not None
    assert set(stored.items) == {keep.variant_id}


async def test_concurrent_mutations_no_lost_update(repo: RedisCartRepository) -> None:
    cart = await repo.new_guest()
    items = [make_item() for _ in range(10)]

    await asyncio.gather(*(repo.mutate(cart.cart_id, put(i)) for i in items))

    stored = await repo.get(cart.cart_id)
    assert stored is not None
    assert set(stored.items) == {i.variant_id for i in items}
    assert stored.version == cart.version + 10


async def test_concurrent_same_sku_increments_no_lost_update(repo: RedisCartRepository) -> None:
    cart = await repo.new_guest()
    snapshot = make_item(available=100)

    def add_one(c: Cart) -> None:
        add_item(c, snapshot, 1, max_lines=50, max_qty=50)

    await asyncio.gather(*(repo.mutate(cart.cart_id, add_one) for _ in range(10)))

    stored = await repo.get(cart.cart_id)
    assert stored is not None
    assert stored.items[snapshot.variant_id].quantity == 10


async def test_noop_mutate_leaves_version_and_ttl(repo: RedisCartRepository, redis: Redis) -> None:
    cart = await repo.new_guest()
    item = make_item()
    await repo.mutate(cart.cart_id, put(item))
    await repo.mutate(cart.cart_id, lambda c: setattr(c, "coupon_code", "BEMVINDO10"))
    header, items = f"cart:{cart.cart_id}", f"cart:{cart.cart_id}:items"
    await redis.expire(header, 100)
    await redis.expire(items, 100)
    before = await repo.get(cart.cart_id)
    assert before is not None

    def same(c: Cart) -> str:
        c.items[item.variant_id] = replace(item)
        c.coupon_code = "BEMVINDO10"
        return "nada"

    assert await repo.mutate(cart.cart_id, same) == "nada"

    assert await repo.get(cart.cart_id) == before
    assert 0 < await redis.ttl(header) <= 100
    assert 0 < await redis.ttl(items) <= 100


async def test_noop_mutate_retries_when_state_changes_between_reads(
    repo: RedisCartRepository, redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    cart = await repo.new_guest()
    items_key = f"cart:{cart.cart_id}:items"
    original = Pipeline.hgetall
    injected = False

    async def hgetall_with_concurrent_write(self: Pipeline, name: str) -> object:
        nonlocal injected
        if name == items_key and not injected:
            injected = True
            # Outra escrita entre a leitura do cabeçalho e a dos itens: estado "rasgado".
            await redis.hset(f"cart:{cart.cart_id}", "coupon_code", "OUTRA-ABA")
        return await original(self, name)  # pyright: ignore[reportGeneralTypeIssues]

    monkeypatch.setattr(Pipeline, "hgetall", hgetall_with_concurrent_write)

    seen = await repo.mutate(cart.cart_id, lambda c: c.coupon_code)
    monkeypatch.undo()  # o wrapper só serve ao modo imediato (WATCH), não ao pipeline do get

    assert injected
    assert seen == "OUTRA-ABA"
    stored = await repo.get(cart.cart_id)
    assert stored is not None
    assert stored.version == 0


async def test_renew_ttl_false_applies_change_and_keeps_ttl(
    repo: RedisCartRepository, redis: Redis
) -> None:
    cart = await repo.new_guest()
    first = make_item()
    await repo.mutate(cart.cart_id, put(first))
    header, items = f"cart:{cart.cart_id}", f"cart:{cart.cart_id}:items"
    await redis.expire(header, 100)
    await redis.expire(items, 100)

    def reprice(c: Cart) -> None:
        c.items[first.variant_id].unit_price_cents = 3990

    await repo.mutate(cart.cart_id, reprice, renew_ttl=False)

    stored = await repo.get(cart.cart_id)
    assert stored is not None
    assert stored.version == 2
    assert stored.items[first.variant_id].unit_price_cents == 3990
    assert 0 < await redis.ttl(header) <= 100
    assert 0 < await redis.ttl(items) <= 100


async def test_renew_ttl_false_new_items_key_gets_header_ttl(
    repo: RedisCartRepository, redis: Redis
) -> None:
    cart = await repo.new_guest()
    header, items = f"cart:{cart.cart_id}", f"cart:{cart.cart_id}:items"
    await redis.expire(header, 100)

    await repo.mutate(cart.cart_id, put(make_item()), renew_ttl=False)

    assert 0 < await redis.ttl(header) <= 100
    assert 0 < await redis.ttl(items) <= 100


async def test_mutate_missing_cart_is_404(repo: RedisCartRepository, redis: Redis) -> None:
    missing = str(uuid.uuid4())

    with pytest.raises(CartError) as exc:
        await repo.mutate(missing, put(make_item()))

    assert exc.value.code == "cart.cart.not_found"
    assert exc.value.extra == {"status": 404}
    assert await redis.keys("*") == []


async def test_fn_raising_leaves_state_unchanged(repo: RedisCartRepository, redis: Redis) -> None:
    cart = await repo.new_guest()
    first = make_item()
    await repo.mutate(cart.cart_id, put(first))
    before = await repo.get(cart.cart_id)
    other = make_item()

    def fn(c: Cart) -> None:
        c.items[other.variant_id] = other
        c.items.pop(first.variant_id)
        raise CartError("cart.item.quantity_limit", max=20)

    with pytest.raises(CartError) as exc:
        await repo.mutate(cart.cart_id, fn)

    assert exc.value.code == "cart.item.quantity_limit"
    assert await repo.get(cart.cart_id) == before
    assert await repo.carts_for_variant(other.variant_id) == set()
    assert await repo.carts_for_variant(first.variant_id) == {cart.cart_id}


async def test_retries_exhausted_is_409(
    repo: RedisCartRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    cart = await repo.new_guest()
    calls = 0

    def fn(c: Cart) -> None:
        nonlocal calls
        calls += 1
        c.coupon_code = "BEMVINDO10"  # mudança real: no-op não chega ao EXEC

    async def always_conflict(*_args: object, **_kwargs: object) -> None:
        raise WatchError("conflito simulado")

    async def no_sleep(_attempt: int) -> None:
        return None

    monkeypatch.setattr("redis.asyncio.client.Pipeline.execute", always_conflict)
    monkeypatch.setattr(redis_repo, "_backoff", no_sleep)

    with pytest.raises(CartError) as exc:
        await repo.mutate(cart.cart_id, fn)

    assert exc.value.code == "cart.cart.concurrent_update"
    assert exc.value.extra == {"status": 409}
    assert calls == 6


async def test_delete_clears_cart_and_index(repo: RedisCartRepository, redis: Redis) -> None:
    user_id = str(uuid.uuid4())
    cart = await repo.cart_for_user(user_id)
    a, b = make_item(), make_item()
    await repo.mutate(cart.cart_id, put(a))
    await repo.mutate(cart.cart_id, put(b))

    await repo.delete(cart.cart_id)

    assert await repo.get(cart.cart_id) is None
    assert await repo.carts_for_variant(a.variant_id) == set()
    assert await repo.carts_for_variant(b.variant_id) == set()
    assert await redis.keys("*") == []


async def test_delete_guest_keeps_other_carts_in_index(repo: RedisCartRepository) -> None:
    shared = make_item()
    one, two = await repo.new_guest(), await repo.new_guest()
    await repo.mutate(one.cart_id, put(shared))
    await repo.mutate(two.cart_id, put(shared))

    await repo.delete(one.cart_id)

    assert await repo.carts_for_variant(shared.variant_id) == {two.cart_id}


async def test_forget_variant_cart_removes_stale_entry(repo: RedisCartRepository) -> None:
    cart = await repo.new_guest()
    item = make_item()
    await repo.mutate(cart.cart_id, put(item))

    await repo.forget_variant_cart(item.variant_id, cart.cart_id)

    assert await repo.carts_for_variant(item.variant_id) == set()


async def test_processed_events_ttl(repo: RedisCartRepository, redis: Redis) -> None:
    event_id = str(uuid.uuid4())
    assert await repo.processed(event_id) is False

    await repo.mark_processed(event_id)

    assert await repo.processed(event_id) is True
    ttl = await redis.ttl(f"processed_events:{event_id}")
    assert 7 * 86400 - 5 < ttl <= 7 * 86400


async def test_discount_cache_keyed_by_version(repo: RedisCartRepository, redis: Redis) -> None:
    cart_id = str(uuid.uuid4())
    value = {"discount_cents": 500, "valid": True}

    assert await repo.cached_discount(cart_id, 3) is None
    await repo.cache_discount(cart_id, 3, value)

    assert await repo.cached_discount(cart_id, 3) == value
    assert await repo.cached_discount(cart_id, 4) is None
    assert 0 < await redis.ttl(f"cart:{cart_id}:discount:3") <= 30


def test_item_json_roundtrip_fully_populated() -> None:
    item = make_item(
        image_url=None,
        unavailable=True,
        archived=True,
        seen_price_cents=3990,
        notice=Notice("price_changed", old_price_cents=3990, new_price_cents=4990),
    )

    assert item_from_json(item_to_json(item)) == item
    reduced = make_item(notice=Notice("quantity_reduced", quantity=2))
    assert item_from_json(item_to_json(reduced)) == reduced


def test_item_json_ignores_unknown_and_defaults_missing_optional_keys() -> None:
    item = make_item()
    raw = json.dumps(
        {
            "variant_id": item.variant_id,
            "product_id": item.product_id,
            "product_slug": "camiseta-basica",
            "name": "Camiseta básica",
            "color_code": "preto",
            "color_name": "Preto",
            "size_code": "M",
            "image_url": "/media/camiseta.jpg",
            "unit_price_cents": 4990,
            "available": 10,
            "category_slug": "camisetas",
            "collection_slugs": ["verao"],
            "quantity": 1,
            "item_version": 1,
            "campo_futuro": 42,
        }
    )

    assert item_from_json(raw) == item
