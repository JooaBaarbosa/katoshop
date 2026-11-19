"""Consumidor dos eventos do catalog (spec §3.3 e §4.6).

Para cada evento, atualiza todos os carrinhos do índice reverso, uma transação Redis por
carrinho (`mutate` sem renovar o TTL do visitante). Idempotência: `processed_events` por `id`
(verificado no início, marcado só depois de todos os carrinhos) mais a guarda de versão
(`data.version`, a versão da variante) e o arquivado sticky (S7) nas funções do domínio.

Erros:
- payload malformado ou tipo desconhecido: loga e marca como processado (mensagem venenosa não
  gira no retry nem enche a DLQ);
- erro transitório (Redis fora, conflito esgotado): sobe, e o `EventConsumer` manda para retry.
"""

import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import structlog

from cart.adapters._service_call import canonical_uuid, int_value
from cart.application.ports import CartRepository
from cart.domain.cart import (
    Cart,
    CartError,
    CartItem,
    apply_archived,
    apply_price_changed,
    apply_stock_changed,
)
from ks_platform.events import Envelope
from ks_platform.messaging import EventConsumer

log = structlog.get_logger()

EXCHANGE = "catalog.events"
QUEUE = "cart.catalog-events"
BINDINGS = ["catalog.variant.*.v1", "catalog.product.archived.v1"]

PRICE_CHANGED = "catalog.variant.price_changed.v1"
STOCK_CHANGED = "catalog.variant.stock_changed.v1"
PRODUCT_ARCHIVED = "catalog.product.archived.v1"

START_RETRY_S = 5.0

type ItemUpdate = Callable[[CartItem], bool]


@dataclass(frozen=True)
class _Plan:
    variant_ids: list[str]
    update: ItemUpdate


def _non_negative(value: object) -> int:
    number = int_value(value)
    if number < 0:
        raise ValueError("inteiro negativo")
    return number


def _plan(event: Envelope) -> _Plan | None:
    """O que aplicar e em quais variantes; `None` para tipo desconhecido.

    Levanta `ValueError` (ou `KeyError`) se o payload não tem o formato do contrato.
    """
    data: dict[str, Any] = event.data
    if event.type == PRICE_CHANGED:
        price, version = _non_negative(data["new_price_cents"]), int_value(data["version"])
        return _Plan(
            [canonical_uuid(data["variant_id"])],
            lambda item: apply_price_changed(item, price, version),
        )
    if event.type == STOCK_CHANGED:
        available, version = _non_negative(data["available"]), int_value(data["version"])
        return _Plan(
            [canonical_uuid(data["variant_id"])],
            lambda item: apply_stock_changed(item, available, version),
        )
    if event.type == PRODUCT_ARCHIVED:
        raw = data["variant_ids"]
        if not isinstance(raw, list):
            raise ValueError("variant_ids inválido")
        return _Plan(list(dict.fromkeys(canonical_uuid(v) for v in raw)), apply_archived)
    return None


def _applier(variant_ids: list[str], update: ItemUpdate) -> Callable[[Cart], None]:
    """Função pura para `mutate`: aplica a atualização às linhas existentes; sem linha, no-op."""

    def fn(cart: Cart) -> None:
        for variant_id in variant_ids:
            item = cart.items.get(variant_id)
            if item is not None:
                update(item)

    return fn


async def handle_catalog_event(event: Envelope, repo: CartRepository) -> None:
    event_id = str(event.id)
    if await repo.processed(event_id):
        return
    try:
        plan = _plan(event)
    except (KeyError, ValueError) as exc:
        log.warning("catalog_event.malformed", event_id=event_id, type=event.type, error=str(exc))
        await repo.mark_processed(event_id)
        return
    if plan is None:
        log.info("catalog_event.unknown_type", event_id=event_id, type=event.type)
        await repo.mark_processed(event_id)
        return

    # Agrupa por carrinho: o arquivamento de um produto vira uma transação por carrinho.
    carts: dict[str, list[str]] = {}
    for variant_id in plan.variant_ids:
        for cart_id in await repo.carts_for_variant(variant_id):
            carts.setdefault(cart_id, []).append(variant_id)

    for cart_id, variant_ids in carts.items():
        try:
            await repo.mutate(cart_id, _applier(variant_ids, plan.update), renew_ttl=False)
        except CartError as exc:
            if exc.code != "cart.cart.not_found":
                raise
            # Carrinho expirado (Review Focus 2): o índice é só uma dica, limpa a entrada órfã.
            # Carrinho existente sem a linha não sai do índice: um SREM aqui correria com um add.
            for variant_id in variant_ids:
                await repo.forget_variant_cart(variant_id, cart_id)
    await repo.mark_processed(event_id)


class CatalogEventsConsumer:
    """Inicia o `EventConsumer` em segundo plano, tentando de novo enquanto o broker está fora.

    Broker fora não impede o cart de subir (a prontidão depende só do Redis). Depois de
    iniciado, a conexão robusta do aio-pika cuida das reconexões.
    """

    def __init__(
        self, amqp_url: str, repo: CartRepository, *, retry_s: float = START_RETRY_S
    ) -> None:
        async def handler(event: Envelope) -> None:
            await handle_catalog_event(event, repo)

        self._consumer = EventConsumer(
            amqp_url, exchange=EXCHANGE, queue=QUEUE, bindings=BINDINGS, handler=handler
        )
        self._retry_s = retry_s
        self._task: asyncio.Task[None] | None = None

    async def _start_until_connected(self) -> None:
        while True:
            try:
                await self._consumer.start()
            except Exception as exc:  # noqa: BLE001 - qualquer falha de conexão: tenta de novo
                log.warning("catalog_consumer.start_failed", error=type(exc).__name__)
                await asyncio.sleep(self._retry_s)
            else:
                log.info("catalog_consumer.started", queue=QUEUE)
                return

    def start(self) -> None:
        self._task = asyncio.create_task(self._start_until_connected(), name="catalog-consumer")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._consumer.stop()
