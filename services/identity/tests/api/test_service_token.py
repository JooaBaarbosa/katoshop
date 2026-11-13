from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from identity.main import create_app
from identity.settings import IdentitySettings
from ks_platform.auth import JwksKeyProvider, ServicePrincipal, TokenVerifier

SECRET = "s" * 40  # noqa: S105 (segredo de teste)


@pytest.fixture
def settings(settings: IdentitySettings) -> IdentitySettings:
    return settings.model_copy(update={"service_clients": {"cart": SECRET}})


async def _post(client: httpx.AsyncClient, **body: str) -> httpx.Response:
    return await client.post("/v1/auth/service-token", json=body)


async def test_issues_token_verifiable_as_service_principal(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    response = await _post(client, client_id="cart", client_secret=SECRET)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"  # noqa: S105
    assert body["expires_in"] == 300

    async def fetch(_url: str) -> dict[str, Any]:
        return {"keys": [app.state.signing_key.public_jwk()]}

    verifier = TokenVerifier(JwksKeyProvider("http://jwks", fetch=fetch))
    principal = await verifier.verify(body["access_token"], "service")
    assert principal == ServicePrincipal("cart")


async def test_wrong_secret_and_unknown_client_have_identical_bodies(
    client: httpx.AsyncClient,
) -> None:
    wrong = await _post(client, client_id="cart", client_secret="x" * 40)
    unknown = await _post(client, client_id="ghost", client_secret=SECRET)

    assert wrong.status_code == unknown.status_code == 401
    a, b = wrong.json(), unknown.json()
    a.pop("trace_id", None)
    b.pop("trace_id", None)
    assert a == b
    assert a["code"] == "identity.service.invalid_client"


async def test_missing_secret_is_422(client: httpx.AsyncClient) -> None:
    response = await _post(client, client_id="cart")

    assert response.status_code == 422
    assert response.json()["code"] == "request.validation"


def test_short_secret_blocks_startup(settings: IdentitySettings) -> None:
    short = settings.model_copy(update={"service_clients": {"cart": "curto"}})

    with pytest.raises(RuntimeError, match="IDENTITY_SERVICE_CLIENTS"):
        create_app(short)
