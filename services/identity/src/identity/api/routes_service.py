import hashlib
import hmac
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, StringConstraints

from identity.domain.tokens import SERVICE_TTL, issue_service_token
from ks_platform.errors import ProblemError

router = APIRouter(prefix="/v1/auth", tags=["auth"])

INVALID_CLIENT = "identity.service.invalid_client"


class ServiceTokenIn(BaseModel):
    client_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    client_secret: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class ServiceTokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


@router.post("/service-token")
async def service_token(body: ServiceTokenIn, request: Request) -> ServiceTokenOut:
    clients: dict[str, str] = request.app.state.settings.service_clients
    expected = clients.get(body.client_id)
    # cliente desconhecido também faz uma comparação, para não vazar a existência pelo tempo
    candidate = expected if expected is not None else ""
    matches = hmac.compare_digest(_digest(candidate), _digest(body.client_secret))
    if expected is None or not matches:
        raise ProblemError(401, INVALID_CLIENT, "Credenciais de serviço inválidas")
    token = issue_service_token(request.app.state.signing_key, body.client_id, datetime.now(UTC))
    return ServiceTokenOut(access_token=token, expires_in=int(SERVICE_TTL.total_seconds()))
