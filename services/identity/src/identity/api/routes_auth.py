from fastapi import APIRouter, Depends, Response

from identity.api.deps import auth_service
from identity.api.errors import mapped
from identity.api.schemas import LoginIn, RefreshIn, RegisterIn, TokenPairOut
from identity.application.auth_service import AuthService

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", status_code=201)
async def register(body: RegisterIn, service: AuthService = Depends(auth_service)) -> TokenPairOut:  # noqa: B008
    pair = await mapped(service.register(body.email, body.password, body.name))
    return TokenPairOut.from_pair(pair)


@router.post("/login")
async def login(body: LoginIn, service: AuthService = Depends(auth_service)) -> TokenPairOut:  # noqa: B008
    # a audiência é fixa por rota: nunca vem do corpo
    pair = await mapped(service.login(body.email, body.password, "storefront"))
    return TokenPairOut.from_pair(pair)


@router.post("/staff/login")
async def staff_login(
    body: LoginIn,
    service: AuthService = Depends(auth_service),  # noqa: B008
) -> TokenPairOut:
    pair = await mapped(service.login(body.email, body.password, "admin"))
    return TokenPairOut.from_pair(pair)


@router.post("/refresh")
async def refresh(body: RefreshIn, service: AuthService = Depends(auth_service)) -> TokenPairOut:  # noqa: B008
    pair = await mapped(service.refresh(body.refresh_token))
    return TokenPairOut.from_pair(pair)


@router.post("/logout", status_code=204)
async def logout(body: RefreshIn, service: AuthService = Depends(auth_service)) -> Response:  # noqa: B008
    await service.logout(body.refresh_token)
    return Response(status_code=204)
