"""Domínio puro do carrinho: sem I/O, só regras sobre itens, avisos e totais."""

from dataclasses import dataclass, field, replace
from typing import Any, Literal

NoticeCode = Literal["price_changed", "quantity_reduced", "unavailable"]


class CartError(Exception):
    """Violação de regra do carrinho; `code` no formato `cart.<área>.<motivo>`."""

    def __init__(self, code: str, **extra: Any) -> None:
        super().__init__(code)
        self.code = code
        self.extra = extra


@dataclass(frozen=True)
class Notice:
    code: NoticeCode
    old_price_cents: int | None = None
    new_price_cents: int | None = None
    quantity: int | None = None


@dataclass
class CartItem:
    variant_id: str
    product_id: str
    product_slug: str
    name: str
    color_code: str
    color_name: str
    size_code: str
    image_url: str | None
    unit_price_cents: int
    available: int
    category_slug: str
    collection_slugs: list[str]
    quantity: int
    # Marcas d'água por tipo de evento (S11): o catalog usa uma única `variants.version` para
    # preço e estoque, e a entrega pode chegar fora de ordem. Cada tipo compara `data.version`
    # só com a sua marca; um evento de estoque mais novo não descarta um de preço mais antigo.
    # O snapshot do catalog (add_item) começa as duas na versão lida.
    price_version: int
    stock_version: int
    unavailable: bool = False
    # Produto arquivado: sticky, só um snapshot novo e ativo (add_item) limpa.
    archived: bool = False
    # Último preço que o cliente viu, guardado quando o preço muda com o item indisponível.
    seen_price_cents: int | None = None
    notice: Notice | None = None

    @property
    def variant_version(self) -> int:
        """Maior versão da variante já aplicada ao item (gravada como `item_version`)."""
        return max(self.price_version, self.stock_version)


@dataclass
class Cart:
    cart_id: str
    owner: str
    items: dict[str, CartItem] = field(default_factory=dict)
    coupon_code: str | None = None
    version: int = 0


_UNAVAILABLE = Notice("unavailable")


def _check_quantity(quantity: int, available: int, max_qty: int) -> None:
    if quantity < 1 or quantity > max_qty:
        raise CartError("cart.item.quantity_limit", max=max_qty)
    if quantity > available:
        raise CartError("cart.item.quantity_exceeds_stock", max=available)


def add_item(
    cart: Cart, snapshot: CartItem, quantity: int, *, max_lines: int, max_qty: int
) -> None:
    """Soma `quantity` ao item; `snapshot` traz os dados atuais lidos do catalog."""
    if snapshot.unavailable or snapshot.available <= 0:
        raise CartError("cart.item.unavailable")
    existing = cart.items.get(snapshot.variant_id)
    if existing is None and len(cart.items) >= max_lines:
        raise CartError("cart.cart.too_many_lines", max=max_lines)
    base = existing.quantity if existing and not existing.unavailable else 0
    total = quantity + base
    _check_quantity(total, snapshot.available, max_qty)
    cart.items[snapshot.variant_id] = replace(snapshot, quantity=total, notice=None)


def set_quantity(cart: Cart, variant_id: str, quantity: int, *, max_qty: int) -> None:
    """Define a quantidade; 0 remove (também se o item já não existir)."""
    item = cart.items.get(variant_id)
    if quantity == 0:
        cart.items.pop(variant_id, None)
        return
    if item is None:
        raise CartError("cart.item.not_found")
    if item.unavailable:
        raise CartError("cart.item.unavailable")
    _check_quantity(quantity, item.available, max_qty)
    item.quantity = quantity
    item.notice = None


def apply_price_changed(item: CartItem, new_price_cents: int, version: int) -> bool:
    if version <= item.price_version:
        return False
    item.price_version = version
    if new_price_cents == item.unit_price_cents:
        return True
    if item.unavailable:
        # Silencioso: o aviso de indisponível fica e o preço visto pelo cliente é guardado.
        if item.seen_price_cents is None:
            item.seen_price_cents = item.unit_price_cents
        item.unit_price_cents = new_price_cents
        return True
    old = item.unit_price_cents
    item.unit_price_cents = new_price_cents
    item.notice = Notice("price_changed", old_price_cents=old, new_price_cents=new_price_cents)
    return True


def apply_stock_changed(item: CartItem, available: int, version: int) -> bool:
    if version <= item.stock_version:
        return False
    item.stock_version = version
    item.available = available
    if item.archived:
        return True
    if available == 0:
        item.unavailable = True
        item.notice = _UNAVAILABLE
    elif item.unavailable:
        item.unavailable = False
        item.quantity = 1
        seen, item.seen_price_cents = item.seen_price_cents, None
        if seen is not None and seen != item.unit_price_cents:
            item.notice = Notice(
                "price_changed", old_price_cents=seen, new_price_cents=item.unit_price_cents
            )
        else:
            item.notice = None
    elif available < item.quantity:
        item.quantity = available
        item.notice = Notice("quantity_reduced", quantity=available)
    return True


def apply_archived(item: CartItem) -> bool:
    """Produto arquivado: sempre aplicado (o evento não tem versão) e permanente no item."""
    item.archived = True
    item.unavailable = True
    item.notice = _UNAVAILABLE
    return True


def _fresher(a: CartItem, g: CartItem) -> CartItem:
    """Junta duas cópias da mesma linha campo a campo pelas marcas d'água (S11).

    Estoque (`available`, `unavailable`, quantidade, avisos) vem da cópia com `stock_version`
    maior; preço (`unit_price_cents`) da com `price_version` maior. Empate fica com a conta
    (`a`). Quando as fontes diferem, o aviso de estoque prevalece; sem aviso de estoque, vale o
    `price_changed` da fonte do preço. Linha indisponível guarda o preço que o cliente viu.
    """
    stock = g if g.stock_version > a.stock_version else a
    price = g if g.price_version > a.price_version else a
    if stock is price:
        return stock
    notice = stock.notice
    if notice is None or notice.code == "price_changed":
        notice = price.notice if price.notice and price.notice.code == "price_changed" else None
    seen = stock.seen_price_cents
    if stock.unavailable and seen is None and stock.unit_price_cents != price.unit_price_cents:
        seen = stock.unit_price_cents
    return replace(
        stock,
        unit_price_cents=price.unit_price_cents,
        price_version=price.price_version,
        seen_price_cents=seen,
        notice=notice,
    )


@dataclass
class MergeResult:
    reduced: list[str] = field(default_factory=list)  # quantidade reduzida (aviso quantity_reduced)
    dropped: list[str] = field(default_factory=list)  # linhas do visitante que não couberam


def merge(account: Cart, guest: Cart, *, max_lines: int, max_qty: int) -> MergeResult:
    """Une o carrinho de visitante no da conta.

    `reduced`: variant_ids com quantidade reduzida (o item já traz o aviso). `dropped`: linhas do
    visitante descartadas por falta de espaço em `max_lines` (o service pode avisar o cliente).
    Linhas disponíveis do visitante entram antes das indisponíveis. Avisos não vistos são mantidos.
    Cupom: o do visitante prevalece quando presente. O service valida o cupom do visitante
    antes e o zera em `guest.coupon_code` se for inválido, o que mantém o da conta.
    """
    result = MergeResult()
    for variant_id, g in sorted(guest.items.items(), key=lambda kv: kv[1].unavailable):
        a = account.items.get(variant_id)
        if a is None:
            if len(account.items) >= max_lines:
                result.dropped.append(variant_id)
                continue
            account.items[variant_id] = g
            if g.quantity > max_qty and not g.unavailable:
                g.quantity = max_qty
                g.notice = Notice("quantity_reduced", quantity=max_qty)
                result.reduced.append(variant_id)
            continue
        fresh = _fresher(a, g)
        if a.archived or g.archived:
            # Arquivado é sticky também no merge (S10): um visitante que perdeu o evento de
            # arquivamento não pode reviver a linha. Os demais campos vêm do mais novo.
            notice = fresh.notice if fresh.archived else _UNAVAILABLE
            account.items[variant_id] = replace(
                fresh, archived=True, unavailable=True, notice=notice
            )
            continue
        if a.unavailable or g.unavailable:
            account.items[variant_id] = fresh
            continue
        total = a.quantity + g.quantity
        capped = min(total, fresh.available, max_qty)
        merged = replace(fresh, quantity=capped)
        if capped < total:
            merged.notice = Notice("quantity_reduced", quantity=capped)
            result.reduced.append(variant_id)
        account.items[variant_id] = merged
    if guest.coupon_code:
        account.coupon_code = guest.coupon_code
    return result


def totals(cart: Cart) -> tuple[int, bool]:
    """(subtotal_cents, checkout_blocked).

    Carrinho vazio não é "bloqueado" aqui (a spec §4.4 só bloqueia por item indisponível;
    o checkout da fatia 3 rejeita carrinho vazio por conta própria).
    """
    items = cart.items.values()
    subtotal = sum(i.unit_price_cents * i.quantity for i in items if not i.unavailable)
    return subtotal, any(i.unavailable for i in items)
