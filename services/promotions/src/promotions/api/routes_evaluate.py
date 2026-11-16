from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ks_platform.auth import ServicePrincipal, require_service
from promotions.api.schemas import EvaluateIn, EvaluateOut
from promotions.application.evaluate_service import EvaluateService
from promotions.domain.coupons import LineItem

router = APIRouter(prefix="/v1/promotions", tags=["internal"])

Caller = Annotated[ServicePrincipal, Depends(require_service())]


def evaluate_service(request: Request) -> EvaluateService:
    service: EvaluateService = request.app.state.evaluate_service
    return service


@router.post("/evaluate")
async def evaluate_coupon(
    body: EvaluateIn,
    _caller: Caller,
    service: Annotated[EvaluateService, Depends(evaluate_service)],
) -> EvaluateOut:
    items = [
        LineItem(
            variant_id=str(i.variant_id),
            unit_price_cents=i.unit_price_cents,
            quantity=i.quantity,
            category_slug=i.category_slug,
            collection_slugs=frozenset(i.collection_slugs),
        )
        for i in body.items
    ]
    result = await service.evaluate(body.code, body.customer_id, items)
    return EvaluateOut.from_result(result)
