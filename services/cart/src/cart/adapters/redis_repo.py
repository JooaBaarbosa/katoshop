"""Repositório do carrinho no Redis (spec §4.1).

Chaves:
- `cart:{id}` (hash): `owner` (`guest:{id}` ou `user:{user_id}`), `coupon_code` (ausente quando
  não há cupom), `version`, `created_at`, `updated_at`;
- `cart:{id}:items` (hash): `variant_id` canônico (UUID minúsculo) -> JSON do item;
- `user:{user_id}:cart` -> `cart_id` do cliente;
- `variant:{variant_id}:carts` (set): índice reverso para o consumidor de eventos;
- `processed_events:{event_id}`: deduplicação de eventos (7 dias);
- `cart:{id}:discount:{version}`: desconto calculado, cache de 30 s.

O índice reverso é uma dica, não uma verdade: um carrinho de visitante expira pelo TTL sem passar
por `delete`, então `carts_for_variant` pode devolver IDs que já não existem. O consumidor
ignora esses IDs e os limpa com `forget_variant_cart`. Por isso os sets do índice não têm TTL:
cada entrada órfã some no primeiro evento da variante.

Carrinho de visitante: as duas chaves (`cart:{id}` e `cart:{id}:items`) recebem o TTL na criação
e em toda mutação. Carrinho de cliente nunca recebe TTL.
"""

import asyncio
import json
import random
import uuid
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from redis.asyncio.client import Pipeline
from redis.exceptions import WatchError
from redis.typing import EncodableT, FieldT

from cart.domain.cart import Cart, CartError, CartItem, Notice

MAX_ATTEMPTS = 6  # 1 tentativa + 5 retentativas (Review Focus 1)
PROCESSED_TTL_S = 7 * 24 * 3600
DISCOUNT_TTL_S = 30
_BACKOFF_BASE_S = 0.025
_BACKOFF_CAP_S = 0.25


def _cart_key(cart_id: str) -> str:
    return f"cart:{cart_id}"


def _items_key(cart_id: str) -> str:
    return f"cart:{cart_id}:items"


def _user_key(user_id: str) -> str:
    return f"user:{user_id}:cart"


def _variant_key(variant_id: str) -> str:
    return f"variant:{variant_id}:carts"


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _backoff(attempt: int) -> None:
    """Espera com jitter (exponencial, com teto) antes de tentar de novo após um conflito."""
    window = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * 2**attempt)
    await asyncio.sleep(random.uniform(0, window))  # noqa: S311 - jitter, não criptografia


# ------------------------------------------------------------------------------ serialização


def item_to_json(item: CartItem) -> str:
    """JSON com chaves estáveis; `item_version` guarda `variant_version` (spec §4.1)."""
    notice = item.notice
    data: dict[str, Any] = {
        "variant_id": item.variant_id,
        "product_id": item.product_id,
        "product_slug": item.product_slug,
        "name": item.name,
        "color_code": item.color_code,
        "color_name": item.color_name,
        "size_code": item.size_code,
        "image_url": item.image_url,
        "unit_price_cents": item.unit_price_cents,
        "available": item.available,
        "category_slug": item.category_slug,
        "collection_slugs": item.collection_slugs,
        "quantity": item.quantity,
        "item_version": item.variant_version,
        "unavailable": item.unavailable,
        "archived": item.archived,
        "seen_price_cents": item.seen_price_cents,
        "notice": None
        if notice is None
        else {
            "code": notice.code,
            "old_price_cents": notice.old_price_cents,
            "new_price_cents": notice.new_price_cents,
            "quantity": notice.quantity,
        },
    }
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def item_from_json(raw: bytes | str) -> CartItem:
    """Lê um item; chaves desconhecidas são ignoradas e as opcionais ausentes têm padrão."""
    data = json.loads(raw)
    notice_data = data.get("notice")
    notice = (
        None
        if notice_data is None
        else Notice(
            code=notice_data["code"],
            old_price_cents=notice_data.get("old_price_cents"),
            new_price_cents=notice_data.get("new_price_cents"),
            quantity=notice_data.get("quantity"),
        )
    )
    return CartItem(
        variant_id=data["variant_id"],
        product_id=data["product_id"],
        product_slug=data["product_slug"],
        name=data["name"],
        color_code=data["color_code"],
        color_name=data["color_name"],
        size_code=data["size_code"],
        image_url=data.get("image_url"),
        unit_price_cents=data["unit_price_cents"],
        available=data["available"],
        category_slug=data["category_slug"],
        collection_slugs=list(data.get("collection_slugs", [])),
        quantity=data["quantity"],
        variant_version=data["item_version"],
        unavailable=data.get("unavailable", False),
        archived=data.get("archived", False),
        seen_price_cents=data.get("seen_price_cents"),
        notice=notice,
    )


def _build_cart(cart_id: str, header: dict[Any, Any], raw_items: dict[Any, Any]) -> Cart:
    fields = {_text(k): _text(v) for k, v in header.items()}
    items = {_text(k): item_from_json(v) for k, v in raw_items.items()}
    return Cart(
        cart_id=cart_id,
        owner=fields["owner"],
        items=items,
        coupon_code=fields.get("coupon_code") or None,
        version=int(fields.get("version", "0")),
    )


def _new_header(owner: str) -> dict[FieldT, EncodableT]:
    now = _now()
    return {"owner": owner, "version": 0, "created_at": now, "updated_at": now}


# ------------------------------------------------------------------------------ repositório


class RedisCartRepository:
    def __init__(self, redis: Redis, *, guest_ttl_s: int) -> None:
        self._redis = redis
        self._guest_ttl_s = guest_ttl_s

    async def _optimistic[T](
        self, keys: Iterable[str], body: Callable[[Pipeline], Awaitable[T]]
    ) -> T:
        """Roda `body` com WATCH em `keys`; conflito (WatchError) tenta de novo até o limite."""
        watched = list(keys)
        for attempt in range(MAX_ATTEMPTS):
            try:
                async with self._redis.pipeline(transaction=True) as pipe:
                    await pipe.watch(*watched)
                    return await body(pipe)
            except WatchError:
                if attempt + 1 < MAX_ATTEMPTS:
                    await _backoff(attempt)
        raise CartError("cart.cart.concurrent_update", status=409)

    async def get(self, cart_id: str) -> Cart | None:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hgetall(_cart_key(cart_id))
            pipe.hgetall(_items_key(cart_id))
            header, raw_items = await pipe.execute()
        if not header:
            return None
        return _build_cart(cart_id, header, raw_items)

    async def new_guest(self) -> Cart:
        cart_id = str(uuid.uuid4())  # opaco e aleatório (exceção ao UUIDv7)
        owner = f"guest:{cart_id}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(_cart_key(cart_id), mapping=_new_header(owner))
            pipe.expire(_cart_key(cart_id), self._guest_ttl_s)
            await pipe.execute()
        return Cart(cart_id=cart_id, owner=owner)

    async def cart_for_user(self, user_id: str) -> Cart:
        """Devolve o carrinho do cliente, criando se não existir.

        Chamadas concorrentes para o mesmo cliente devolvem o mesmo carrinho: a criação grava o
        ponteiro `user:{id}:cart` sob WATCH, e quem perde a corrida relê o ponteiro.
        """
        pointer = _user_key(user_id)
        owner = f"user:{user_id}"

        async def ensure(pipe: Pipeline) -> str:
            current = await pipe.get(pointer)
            if current is not None:
                cart_id = _text(current)
                if await pipe.exists(_cart_key(cart_id)):
                    return cart_id
            cart_id = str(uuid.uuid7())
            pipe.multi()
            pipe.set(pointer, cart_id)
            pipe.hset(_cart_key(cart_id), mapping=_new_header(owner))
            await pipe.execute()
            return cart_id

        for _ in range(MAX_ATTEMPTS):
            cart = await self.get(await self._optimistic((pointer,), ensure))
            if cart is not None:
                return cart
            # Apagado entre a criação e a leitura: tenta de novo.
        raise CartError("cart.cart.concurrent_update", status=409)

    async def mutate[T](
        self, cart_id: str, fn: Callable[[Cart], T], *, renew_ttl: bool = True
    ) -> T:
        """Lê, aplica `fn` e grava só o que mudou, numa transação MULTI.

        `fn` pode rodar mais de uma vez (retentativa), então não deve ter efeitos colaterais.
        Só itens e `coupon_code` são gravados: mudanças de `fn` em `cart.owner` ou
        `cart.version` são ignoradas. Se nada mudou, nada é escrito (versão e TTL ficam como
        estão). `renew_ttl=False` (consumidor de eventos) grava a mudança mas mantém o TTL
        restante do visitante: só o uso pelo cliente renova o prazo (spec §4.1).
        """
        header_key, items_key = _cart_key(cart_id), _items_key(cart_id)

        async def body(pipe: Pipeline) -> T:
            header = await pipe.hgetall(header_key)
            if not header:
                raise CartError("cart.cart.not_found", status=404)
            cart = _build_cart(cart_id, header, await pipe.hgetall(items_key))
            version, owner, coupon = cart.version, cart.owner, cart.coupon_code
            before = {vid: item_to_json(item) for vid, item in cart.items.items()}
            result = fn(cart)
            after = {vid: item_to_json(item) for vid, item in cart.items.items()}
            changed: dict[FieldT, EncodableT] = {
                vid: raw for vid, raw in after.items() if before.get(vid) != raw
            }
            removed = before.keys() - after.keys()
            added = after.keys() - before.keys()
            if not changed and not removed and cart.coupon_code == coupon:
                await pipe.unwatch()
                return result
            guest = owner.startswith("guest:")
            # Sem renovar: as duas chaves seguem o prazo restante do cabeçalho (a de itens pode
            # nascer agora, sem TTL).
            remaining_ms = await pipe.pttl(header_key) if guest and not renew_ttl else None

            pipe.multi()
            if changed:
                pipe.hset(items_key, mapping=changed)
            if removed:
                pipe.hdel(items_key, *removed)
            pipe.hset(header_key, mapping={"version": version + 1, "updated_at": _now()})
            if cart.coupon_code is None:
                pipe.hdel(header_key, "coupon_code")
            else:
                pipe.hset(header_key, "coupon_code", cart.coupon_code)
            for vid in added:
                pipe.sadd(_variant_key(vid), cart_id)
            for vid in removed:
                pipe.srem(_variant_key(vid), cart_id)
            if guest and renew_ttl:
                pipe.expire(header_key, self._guest_ttl_s)
                pipe.expire(items_key, self._guest_ttl_s)
            elif remaining_ms is not None and remaining_ms > 0:
                pipe.pexpire(header_key, remaining_ms)
                pipe.pexpire(items_key, remaining_ms)
            await pipe.execute()
            return result

        return await self._optimistic((header_key, items_key), body)

    async def delete(self, cart_id: str) -> None:
        """Apaga cabeçalho, itens, as entradas do índice reverso e o ponteiro do cliente."""
        header_key, items_key = _cart_key(cart_id), _items_key(cart_id)

        async def body(pipe: Pipeline) -> None:
            owner = await pipe.hget(header_key, "owner")
            variant_ids = [_text(v) for v in await pipe.hkeys(items_key)]
            pointer: str | None = None
            if owner is not None and _text(owner).startswith("user:"):
                pointer = _user_key(_text(owner).removeprefix("user:"))
                await pipe.watch(pointer)
                current = await pipe.get(pointer)
                if current is None or _text(current) != cart_id:
                    pointer = None
            pipe.multi()
            pipe.delete(header_key, items_key)
            for vid in variant_ids:
                pipe.srem(_variant_key(vid), cart_id)
            if pointer is not None:
                pipe.delete(pointer)
            await pipe.execute()

        await self._optimistic((header_key, items_key), body)

    async def carts_for_variant(self, variant_id: str) -> set[str]:
        """IDs de carrinho com a variante; pode incluir carrinhos de visitante já expirados."""
        members = await self._redis.smembers(_variant_key(variant_id))
        return {_text(m) for m in members}

    async def forget_variant_cart(self, variant_id: str, cart_id: str) -> None:
        await self._redis.srem(_variant_key(variant_id), cart_id)

    async def processed(self, event_id: str) -> bool:
        return bool(await self._redis.exists(f"processed_events:{event_id}"))

    async def mark_processed(self, event_id: str) -> None:
        await self._redis.set(f"processed_events:{event_id}", "1", ex=PROCESSED_TTL_S)

    async def cached_discount(self, cart_id: str, version: int) -> dict[str, Any] | None:
        """Desconto em cache para esta versão do carrinho; outra versão é miss."""
        raw = await self._redis.get(f"cart:{cart_id}:discount:{version}")
        return None if raw is None else json.loads(raw)

    async def cache_discount(self, cart_id: str, version: int, value: dict[str, Any]) -> None:
        await self._redis.set(
            f"cart:{cart_id}:discount:{version}", json.dumps(value), ex=DISCOUNT_TTL_S
        )
