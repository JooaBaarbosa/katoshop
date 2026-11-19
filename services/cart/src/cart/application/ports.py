from collections.abc import Callable
from typing import Any, Protocol

from cart.domain.cart import Cart


class CartRepository(Protocol):
    """Persistência do carrinho com lock otimista.

    `mutate` pode chamar `fn` mais de uma vez (retentativa após conflito), então `fn` deve só
    alterar o `Cart` recebido, sem efeitos colaterais. Se `fn` levantar `CartError`, nada é
    gravado e o erro sobe. Só itens e `coupon_code` são gravados (mudanças em `owner` e
    `version` são ignoradas); se nada mudou, nada é escrito. `renew_ttl=False` grava a mudança
    sem renovar o TTL do visitante (consumidor de eventos).
    """

    async def get(self, cart_id: str) -> Cart | None: ...

    async def cart_for_user(self, user_id: str) -> Cart: ...

    async def new_guest(self) -> Cart: ...

    async def mutate[T](
        self, cart_id: str, fn: Callable[[Cart], T], *, renew_ttl: bool = True
    ) -> T: ...

    async def delete(self, cart_id: str) -> None: ...

    async def carts_for_variant(self, variant_id: str) -> set[str]: ...

    async def forget_variant_cart(self, variant_id: str, cart_id: str) -> None: ...

    async def processed(self, event_id: str) -> bool: ...

    async def mark_processed(self, event_id: str) -> None: ...

    async def cached_discount(self, cart_id: str, version: int) -> dict[str, Any] | None: ...

    async def cache_discount(self, cart_id: str, version: int, value: dict[str, Any]) -> None: ...
