from collections.abc import Awaitable

from ks_platform.errors import ProblemError
from promotions.application import admin_service as codes
from promotions.application.admin_service import CouponError

_STATUS: dict[str, tuple[int, str]] = {
    codes.COUPON_NOT_FOUND: (404, "Cupom não encontrado"),
    codes.COUPON_CODE_TAKEN: (409, "Código de cupom já usado"),
    codes.COUPON_VERSION_CONFLICT: (409, "Cupom alterado por outra pessoa"),
    codes.COUPON_HAS_REDEMPTIONS: (409, "Cupom com resgates não pode ser excluído"),
    codes.COUPON_CODE_IMMUTABLE: (422, "O código do cupom não pode ser alterado"),
    codes.REQUEST_VALIDATION: (422, "Requisição inválida"),
}


def to_problem(error: CouponError) -> ProblemError:
    status, title = _STATUS.get(error.code, (422, "Operação inválida"))
    return ProblemError(status, error.code, title, errors=error.errors)


async def mapped[T](call: Awaitable[T]) -> T:
    try:
        return await call
    except CouponError as exc:
        raise to_problem(exc) from exc
