"""Rotas do carrinho (spec §4.3). Todas devolvem o carrinho resultante (`CartOut`)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from cart.api.schemas import AddItemIn, CartOut, CouponIn, MergeIn, MergeOut, QuantityIn
from cart.application.cart_service import CartService, Identity, parse_guest_cart_id
from cart.settings import CartSettings
from ks_platform.auth import Principal, require_audience

router = APIRouter(prefix="/v1/cart", tags=["cart"])

_storefront = require_audience("storefront")


async def optional_storefront_principal(request: Request) -> Principal | None:
    """Ruling S2: sem Authorization é visitante (None); token inválido ou expirado dá 401
    (o BFF renova a sessão); token de outra audiência dá 403."""
    if "authorization" not in request.headers:
        return None
    return await _storefront(request)


async def identity(
    principal: Annotated[Principal | None, Depends(optional_storefront_principal)],
    x_cart_id: Annotated[str | None, Header()] = None,
) -> Identity:
    # Com token, o X-Cart-Id é ignorado: unir o carrinho do visitante é explícito (merge).
    if principal is not None:
        return Identity(user_id=str(principal.user_id))
    if x_cart_id is None:
        return Identity()
    return Identity(guest_cart_id=parse_guest_cart_id(x_cart_id))


def cart_service(request: Request) -> CartService:
    state = request.app.state
    settings: CartSettings = state.settings
    return CartService(
        state.cart_repository,
        state.catalog,
        state.promotions,
        max_lines=settings.max_lines,
        max_qty=settings.max_qty,
    )


Who = Annotated[Identity, Depends(identity)]
Service = Annotated[CartService, Depends(cart_service)]
Customer = Annotated[Principal, Depends(_storefront)]


@router.get("")
async def get_cart(who: Who, service: Service) -> CartOut:
    return CartOut.from_view(await service.view(who))


@router.post("/items")
async def add_item(body: AddItemIn, who: Who, service: Service) -> CartOut:
    return CartOut.from_view(await service.add_item(who, str(body.variant_id), body.quantity))


# Antes de /items/{variant_id}, que não casaria mesmo assim (o parâmetro é UUID).
@router.delete("/items/unavailable")
async def remove_unavailable(who: Who, service: Service) -> CartOut:
    return CartOut.from_view(await service.remove_unavailable(who))


@router.patch("/items/{variant_id}")
async def set_quantity(
    variant_id: uuid.UUID, body: QuantityIn, who: Who, service: Service
) -> CartOut:
    return CartOut.from_view(await service.set_quantity(who, str(variant_id), body.quantity))


@router.delete("/items/{variant_id}")
async def remove_item(variant_id: uuid.UUID, who: Who, service: Service) -> CartOut:
    return CartOut.from_view(await service.remove_item(who, str(variant_id)))


@router.post("/notices/ack")
async def ack_notices(who: Who, service: Service) -> CartOut:
    return CartOut.from_view(await service.ack_notices(who))


@router.put("/coupon")
async def apply_coupon(body: CouponIn, who: Who, service: Service) -> CartOut:
    return CartOut.from_view(await service.apply_coupon(who, body.code))


@router.delete("/coupon")
async def remove_coupon(who: Who, service: Service) -> CartOut:
    return CartOut.from_view(await service.remove_coupon(who))


@router.post("/merge")
async def merge_cart(body: MergeIn, customer: Customer, service: Service) -> MergeOut:
    guest_cart_id = parse_guest_cart_id(body.guest_cart_id)
    view, report = await service.merge(str(customer.user_id), guest_cart_id)
    return MergeOut.from_merge(view, report)
