"""Casos de uso do carrinho: identidade, itens, cupom (com cache de 30 s) e merge no login.

Toda leitura de catalog e promotions acontece antes do `repo.mutate`, porque a função passada a
ele pode rodar mais de uma vez (retentativa do lock otimista) e não pode fazer I/O.
"""

import re
import uuid
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass, field

from cart.adapters.promotions_client import CouponResult
from cart.application.ports import CartRepository, CatalogPort, PromotionsPort
from cart.domain.cart import Cart, CartError, MergeResult, add_item, merge, set_quantity, totals

PROMOTIONS_UNAVAILABLE = "promotions.unavailable"
COUPON_NOT_FOUND = "promotions.coupon.not_found"
NO_ELIGIBLE_ITEMS = "promotions.coupon.no_eligible_items"
_COUPON_RE = re.compile(r"^[A-Z0-9-]{3,32}$")
_GUEST_PREFIX = "guest:"
_USER_PREFIX = "user:"
_UUID_TEXT_LENGTH = 36


def normalize_coupon_code(raw: str) -> str:
    """Mesma regra do promotions: `strip().upper()`, só ASCII, `^[A-Z0-9-]{3,32}$`."""
    stripped = raw.strip()
    code = stripped.upper()
    if not stripped.isascii() or not _COUPON_RE.fullmatch(code):
        raise ValueError("código de cupom inválido")
    return code


def parse_guest_cart_id(value: str) -> str | None:
    """Valida o `X-Cart-Id` (ou `guest_cart_id` do merge).

    Fora do texto canônico de UUID (minúsculo, com hífens): 422 `cart.cart.invalid_id`. UUID
    válido mas não v4 (ex.: o UUIDv7 de um carrinho de cliente) nunca é de visitante: `None`,
    tratado como carrinho inexistente.
    """
    if len(value) != _UUID_TEXT_LENGTH:
        raise CartError("cart.cart.invalid_id", status=422)
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise CartError("cart.cart.invalid_id", status=422) from exc
    if str(parsed) != value:
        raise CartError("cart.cart.invalid_id", status=422)
    return value if parsed.version == 4 else None


@dataclass(frozen=True)
class Identity:
    """Quem chama: cliente logado (`user_id`) ou visitante (`guest_cart_id`, já validado)."""

    user_id: str | None = None
    guest_cart_id: str | None = None


@dataclass(frozen=True)
class CouponView:
    code: str
    valid: bool
    reason: str | None
    min_order_cents: int | None


@dataclass(frozen=True)
class CartView:
    cart: Cart | None
    subtotal_cents: int = 0
    discount_cents: int = 0
    total_cents: int = 0
    checkout_blocked: bool = False
    coupon: CouponView | None = None
    line_discounts: dict[str, int] = field(default_factory=dict)


def _customer_id(cart: Cart) -> str | None:
    return cart.owner.removeprefix(_USER_PREFIX) if cart.owner.startswith(_USER_PREFIX) else None


def _result_from_cache(data: dict[str, object]) -> CouponResult:
    return CouponResult(**data)  # pyright: ignore[reportArgumentType]


class CartService:
    def __init__(
        self,
        repo: CartRepository,
        catalog: CatalogPort,
        promotions: PromotionsPort,
        *,
        max_lines: int,
        max_qty: int,
    ) -> None:
        self._repo = repo
        self._catalog = catalog
        self._promotions = promotions
        self._max_lines = max_lines
        self._max_qty = max_qty

    # ------------------------------------------------------------------ leitura

    async def _guest(self, cart_id: str) -> Cart | None:
        """Só carrinhos de visitante: ID inexistente ou de cliente é tratado como sem carrinho."""
        cart = await self._repo.get(cart_id)
        if cart is None or not cart.owner.startswith(_GUEST_PREFIX):
            return None
        return cart

    async def _resolve(self, identity: Identity) -> Cart | None:
        if identity.user_id is not None:
            return await self._repo.cart_for_user(identity.user_id)
        if identity.guest_cart_id is not None:
            return await self._guest(identity.guest_cart_id)
        return None

    async def view(self, identity: Identity) -> CartView:
        return await self._render(await self._resolve(identity))

    async def _evaluate(self, cart: Cart, code: str, *, read: bool = False) -> CouponResult:
        items = list(cart.items.values())
        if not any(not i.unavailable for i in items):
            return CouponResult(valid=False, reason=NO_ELIGIBLE_ITEMS)
        return await self._promotions.evaluate(code, _customer_id(cart), items, read=read)

    async def _coupon(self, cart: Cart, code: str) -> CouponResult:
        """Avaliação com cache de 30 s por versão do carrinho (spec §4.5).

        Só monta a resposta: orçamento curto de leitura (S12), degrada para desconto 0.
        """
        cached = await self._repo.cached_discount(cart.cart_id, cart.version)
        if cached is not None:
            return _result_from_cache(cached)
        result = await self._evaluate(cart, code, read=True)
        await self._cache(cart, result)
        return result

    async def _cache(self, cart: Cart, result: CouponResult) -> None:
        # Falha do promotions não entra no cache: o próximo GET tenta de novo.
        if result.reason != PROMOTIONS_UNAVAILABLE:
            await self._repo.cache_discount(cart.cart_id, cart.version, asdict(result))

    async def _render(self, cart: Cart | None) -> CartView:
        if cart is None:
            return CartView(cart=None)
        subtotal, blocked = totals(cart)
        coupon_view: CouponView | None = None
        discount = 0
        line_discounts: dict[str, int] = {}
        if cart.coupon_code:
            result = await self._coupon(cart, cart.coupon_code)
            coupon_view = CouponView(
                cart.coupon_code, result.valid, result.reason, result.min_order_cents
            )
            if result.valid:
                discount = min(max(result.discount_cents, 0), subtotal)
                line_discounts = dict(result.per_item)
        return CartView(
            cart=cart,
            subtotal_cents=subtotal,
            discount_cents=discount,
            total_cents=max(subtotal - discount, 0),
            checkout_blocked=blocked,
            coupon=coupon_view,
            line_discounts=line_discounts,
        )

    async def _reload(self, cart_id: str) -> CartView:
        return await self._render(await self._repo.get(cart_id))

    async def _edit(self, identity: Identity, fn: Callable[[Cart], None]) -> CartView:
        """Muda um carrinho existente; sem carrinho devolve o vazio sem criar nada."""
        cart = await self._resolve(identity)
        if cart is None:
            return CartView(cart=None)
        await self._repo.mutate(cart.cart_id, fn)
        return await self._reload(cart.cart_id)

    # ------------------------------------------------------------------ itens

    async def add_item(self, identity: Identity, variant_id: str, quantity: int) -> CartView:
        snapshot = await self._catalog.variant(variant_id)
        if snapshot is None:
            raise CartError("cart.item.not_found", status=404)
        limits = {"max_lines": self._max_lines, "max_qty": self._max_qty}
        cart = await self._resolve(identity)
        if cart is None:
            # Valida antes de criar: uma inclusão recusada não deixa carrinho vazio no Redis.
            add_item(Cart(cart_id="", owner=""), snapshot, quantity, **limits)
            cart = await self._repo.new_guest()
        await self._repo.mutate(cart.cart_id, lambda c: add_item(c, snapshot, quantity, **limits))
        return await self._reload(cart.cart_id)

    async def set_quantity(self, identity: Identity, variant_id: str, quantity: int) -> CartView:
        cart = await self._resolve(identity)
        if cart is None:
            if quantity == 0:
                return CartView(cart=None)
            raise CartError("cart.item.not_found", status=404)
        await self._repo.mutate(
            cart.cart_id,
            lambda c: set_quantity(c, variant_id, quantity, max_qty=self._max_qty),
        )
        return await self._reload(cart.cart_id)

    async def remove_item(self, identity: Identity, variant_id: str) -> CartView:
        return await self.set_quantity(identity, variant_id, 0)

    async def remove_unavailable(self, identity: Identity) -> CartView:
        def drop(cart: Cart) -> None:
            for vid in [vid for vid, item in cart.items.items() if item.unavailable]:
                del cart.items[vid]

        return await self._edit(identity, drop)

    async def ack_notices(self, identity: Identity) -> CartView:
        """Limpa todos os avisos (spec §4.4). O estado `unavailable` do item continua."""

        def clear(cart: Cart) -> None:
            for item in cart.items.values():
                item.notice = None

        return await self._edit(identity, clear)

    # ------------------------------------------------------------------ cupom

    async def apply_coupon(self, identity: Identity, raw_code: str) -> CartView:
        try:
            code = normalize_coupon_code(raw_code)
        except ValueError as exc:
            raise CartError("cart.coupon.invalid", reason=COUPON_NOT_FOUND) from exc
        cart = await self._resolve(identity)
        result = (
            CouponResult(valid=False, reason=NO_ELIGIBLE_ITEMS)
            if cart is None
            else await self._evaluate(cart, code)
        )
        if result.reason == PROMOTIONS_UNAVAILABLE:
            raise CartError("cart.promotions.unavailable", status=503)
        if cart is None or not result.valid:
            raise CartError(
                "cart.coupon.invalid", reason=result.reason, min_order_cents=result.min_order_cents
            )

        def store(c: Cart) -> None:
            c.coupon_code = code

        await self._repo.mutate(cart.cart_id, store)
        after = await self._repo.get(cart.cart_id)
        if after is not None and after.coupon_code == code and after.items == cart.items:
            # Os itens avaliados são os gravados: o GET seguinte reaproveita a avaliação.
            await self._cache(after, result)
        return await self._render(after)

    async def remove_coupon(self, identity: Identity) -> CartView:
        def clear(cart: Cart) -> None:
            cart.coupon_code = None

        return await self._edit(identity, clear)

    # ------------------------------------------------------------------ merge

    async def merge(self, user_id: str, guest_cart_id: str | None) -> tuple[CartView, MergeResult]:
        """Une o carrinho de visitante no da conta e apaga o do visitante.

        ID inexistente ou de cliente: devolve o carrinho da conta sem mudança (relogin
        idempotente). O cupom do visitante só fica se ainda for válido para a conta, avaliado
        sobre o resultado do merge; senão fica o da conta.
        """
        account = await self._repo.cart_for_user(user_id)
        guest = None if guest_cart_id is None else await self._guest(guest_cart_id)
        if guest is None:
            return await self._render(account), MergeResult()
        limits = {"max_lines": self._max_lines, "max_qty": self._max_qty}
        evaluated = guest.coupon_code
        keep_coupon = False
        if evaluated:
            preview = deepcopy(account)
            merge(preview, deepcopy(guest), **limits)
            preview.coupon_code = evaluated
            result = await self._evaluate(preview, evaluated)
            if result.reason == PROMOTIONS_UNAVAILABLE:
                # Sem como validar agora: não troca um cupom da conta por um não verificado.
                keep_coupon = account.coupon_code is None
            else:
                keep_coupon = result.valid

        def combine(cart: Cart, current_guest: Cart) -> MergeResult:
            incoming = deepcopy(current_guest)  # merge altera os itens recebidos
            # Cupom do visitante trocado depois da avaliação: não foi validado, fica o da conta.
            if not (keep_coupon and incoming.coupon_code == evaluated):
                incoming.coupon_code = None
            return merge(cart, incoming, **limits)

        report = await self._repo.merge_guest(account.cart_id, guest.cart_id, combine)
        return await self._reload(account.cart_id), report or MergeResult()
