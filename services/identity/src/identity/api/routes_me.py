from fastapi import APIRouter, Depends, Request

from identity.api.deps import auth_service
from identity.api.errors import mapped
from identity.api.schemas import MePatchIn, UserOut
from identity.application.auth_service import AuthService
from ks_platform.auth import Principal, require_audience
from ks_platform.errors import ProblemError

router = APIRouter(prefix="/v1/me", tags=["me"])

_storefront = require_audience("storefront")
_admin = require_audience("admin")


async def any_principal(request: Request) -> Principal:
    """Aceita token de qualquer audiência (loja ou admin); 401/403 seguem a regra do platform."""
    try:
        return await _storefront(request)
    except ProblemError as exc:
        if exc.status != 403:  # 403 = assinatura válida em outra audiência: tenta a outra
            raise
    return await _admin(request)


@router.get("")
async def get_me(
    principal: Principal = Depends(any_principal),  # noqa: B008
    service: AuthService = Depends(auth_service),  # noqa: B008
) -> UserOut:
    user = await service.get_user(principal.user_id)
    if user is None or user.status != "active":
        raise ProblemError(401, "auth.invalid_token", "Token inválido")
    return UserOut.from_record(user)


@router.patch("")
async def patch_me(
    body: MePatchIn,
    principal: Principal = Depends(any_principal),  # noqa: B008
    service: AuthService = Depends(auth_service),  # noqa: B008
) -> UserOut:
    user = await mapped(
        service.update_profile(
            principal.user_id,
            name=body.name,
            email=body.email,
            new_password=body.new_password,
            current_password=body.current_password,
        ),
        password_field="body.new_password",  # noqa: S106
    )
    return UserOut.from_record(user)
