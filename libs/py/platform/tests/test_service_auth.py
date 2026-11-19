import asyncio
import json
import logging
import time
import uuid

import httpx
import jwt
import pytest
from _helpers import FakeFetch, Signer
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from ks_platform.auth import JwksKeyProvider, ServicePrincipal, TokenVerifier, require_service
from ks_platform.errors import ProblemError, install_problem_handlers
from ks_platform.service_tokens import ServiceTokenProvider


def _service_token(signer: Signer, **overrides: object) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "sub": "cart",
        "aud": "service",
        "iss": "katoshop-identity",
        "iat": now,
        "exp": now + 300,
        "jti": str(uuid.uuid4()),
        "roles": [],
        "kind": "service",
    }
    claims.update(overrides)
    return jwt.encode(claims, signer.private, algorithm="EdDSA", headers={"kid": signer.kid})


def _app(signer: Signer) -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)
    app.state.token_verifier = TokenVerifier(
        JwksKeyProvider("http://identity/jwks", fetch=FakeFetch({"keys": [signer.jwk]}))
    )

    @app.get("/internal")
    async def internal(
        service: ServicePrincipal = Depends(require_service()),  # noqa: B008
    ) -> dict[str, str]:
        return {"client_id": service.client_id}

    return app


async def _get(app: FastAPI, token: str | None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        return await client.get("/internal", headers=headers)


async def test_require_service_accepts_service_token() -> None:
    signer = Signer()
    resp = await _get(_app(signer), _service_token(signer))
    assert resp.status_code == 200
    assert resp.json() == {"client_id": "cart"}


async def test_require_service_rejects_storefront_token_403() -> None:
    signer = Signer()
    resp = await _get(_app(signer), signer.token(aud="storefront", kind="customer"))
    assert resp.status_code == 403
    assert resp.json()["code"] == "auth.forbidden"


async def test_require_service_missing_token_401() -> None:
    resp = await _get(_app(Signer()), None)
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.missing_token"


async def test_require_service_invalid_token_401() -> None:
    resp = await _get(_app(Signer()), "garbage")
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.invalid_token"


async def test_service_token_with_uuid_sub_still_service() -> None:
    signer = Signer()
    resp = await _get(_app(signer), _service_token(signer, sub=str(uuid.uuid4())))
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "overrides",
    [{"kind": "customer"}, {"sub": ""}, {"sub": "x" * 65}, {"sub": 5}],
)
async def test_service_audience_with_bad_claims_rejected(overrides: dict[str, object]) -> None:
    signer = Signer()
    resp = await _get(_app(signer), _service_token(signer, **overrides))
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.invalid_token"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class TokenServer:
    def __init__(self, status: int = 200, expires_in: int = 300) -> None:
        self.calls = 0
        self.status = status
        self.expires_in = expires_in
        self.bodies: list[dict[str, str]] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        self.bodies.append(json.loads(request.content))
        await asyncio.sleep(0)
        if self.status != 200:
            return httpx.Response(self.status)
        return httpx.Response(
            200, json={"access_token": f"tok{self.calls}", "expires_in": self.expires_in}
        )


def _provider(server: TokenServer, clock: FakeClock) -> ServiceTokenProvider:
    http = httpx.AsyncClient(transport=httpx.MockTransport(server))
    return ServiceTokenProvider(
        "http://identity/v1/auth/service-token", "cart", "s3cret", http=http, clock=clock
    )


async def test_provider_caches_until_30s_before_expiry() -> None:
    server, clock = TokenServer(), FakeClock()
    provider = _provider(server, clock)
    assert await provider.token() == "tok1"
    assert server.bodies[0] == {"client_id": "cart", "client_secret": "s3cret"}
    clock.now = 269
    assert await provider.token() == "tok1"
    assert server.calls == 1
    clock.now = 271
    assert await provider.token() == "tok2"
    assert server.calls == 2


async def test_provider_concurrent_calls_share_refresh() -> None:
    server, clock = TokenServer(), FakeClock()
    provider = _provider(server, clock)
    tokens = await asyncio.gather(*(provider.token() for _ in range(5)))
    assert tokens == ["tok1"] * 5
    assert server.calls == 1


async def test_provider_5xx_raises_503() -> None:
    provider = _provider(TokenServer(status=502), FakeClock())
    with pytest.raises(ProblemError) as exc:
        await provider.token()
    assert (exc.value.status, exc.value.code) == (503, "auth.service_token_unavailable")


async def test_provider_network_failure_raises_503() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    provider = ServiceTokenProvider(
        "http://identity/x",
        "cart",
        "s",
        http=httpx.AsyncClient(transport=httpx.MockTransport(boom)),
    )
    with pytest.raises(ProblemError) as exc:
        await provider.token()
    assert (exc.value.status, exc.value.code) == (503, "auth.service_token_unavailable")


async def test_provider_logs_identity_status_and_problem_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Segredo divergente (CART_CLIENT_SECRET x IDENTITY_SERVICE_CLIENTS) precisa ser diagnosticável.
    def reject(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": "identity.service.invalid_client", "status": 401})

    provider = ServiceTokenProvider(
        "http://identity/v1/auth/service-token",
        "cart",
        "s3cret",
        http=httpx.AsyncClient(transport=httpx.MockTransport(reject)),
    )
    with caplog.at_level(logging.WARNING, logger="ks_platform.service_tokens"):
        with pytest.raises(ProblemError):
            await provider.token()
    (record,) = caplog.records
    message = record.getMessage()
    assert "status=401" in message
    assert "code=identity.service.invalid_client" in message
    assert "client_id=cart" in message
    assert "s3cret" not in message


async def test_provider_logs_network_failure_without_status(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    provider = ServiceTokenProvider(
        "http://identity/x",
        "cart",
        "s",
        http=httpx.AsyncClient(transport=httpx.MockTransport(boom)),
    )
    with caplog.at_level(logging.WARNING, logger="ks_platform.service_tokens"):
        with pytest.raises(ProblemError):
            await provider.token()
    (record,) = caplog.records
    assert "error=ConnectError" in record.getMessage()


async def test_provider_failure_does_not_poison_cache() -> None:
    server, clock = TokenServer(status=503), FakeClock()
    provider = _provider(server, clock)
    with pytest.raises(ProblemError):
        await provider.token()
    server.status = 200
    assert await provider.token() == "tok2"


def _provider_with_body(body: dict[str, object], clock: FakeClock) -> ServiceTokenProvider:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=body)

    provider = ServiceTokenProvider(
        "http://identity/x",
        "cart",
        "s",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        clock=clock,
    )
    provider.calls = calls  # type: ignore[attr-defined]
    return provider


async def test_provider_short_ttl_cached_for_half_then_refreshed() -> None:
    server, clock = TokenServer(expires_in=10), FakeClock()
    provider = _provider(server, clock)
    await provider.token()
    clock.now = 4.9
    await provider.token()
    assert server.calls == 1
    clock.now = 5.1
    assert await provider.token() == "tok2"


@pytest.mark.parametrize(
    "body",
    [
        {"access_token": "t", "expires_in": 0},
        {"access_token": "t", "expires_in": -5},
        {"access_token": "t"},
        {"access_token": "t", "expires_in": True},
        {"access_token": "t", "expires_in": "300"},
        {"access_token": "t", "expires_in": float("inf")},
        {"access_token": "t", "expires_in": float("nan")},
        {"access_token": "", "expires_in": 300},
    ],
)
async def test_provider_invalid_expires_in_raises_503(body: dict[str, object]) -> None:
    provider = _provider_with_body(body, FakeClock())
    with pytest.raises(ProblemError) as exc:
        await provider.token()
    assert (exc.value.status, exc.value.code) == (503, "auth.service_token_unavailable")


async def test_provider_huge_ttl_is_capped_to_one_hour() -> None:
    clock = FakeClock()
    provider = _provider_with_body({"access_token": "t", "expires_in": 1e308}, clock)
    await provider.token()
    clock.now = 3600
    await provider.token()
    assert provider.calls["n"] == 2  # type: ignore[attr-defined]


async def test_provider_aclose_closes_only_owned_client() -> None:
    http = httpx.AsyncClient()
    await ServiceTokenProvider("http://x", "c", "s", http=http).aclose()
    assert not http.is_closed
    await http.aclose()
    owned = ServiceTokenProvider("http://x", "c", "s")
    await owned.aclose()
    assert owned._http.is_closed  # pyright: ignore[reportPrivateUsage]


async def test_provider_invalidate_forces_new_token() -> None:
    server, clock = TokenServer(), FakeClock()
    provider = _provider(server, clock)
    assert await provider.token() == "tok1"
    provider.invalidate()
    assert await provider.token() == "tok2"
    assert server.calls == 2


async def test_provider_invalidate_with_stale_token_keeps_newer_token() -> None:
    server, clock = TokenServer(), FakeClock()
    provider = _provider(server, clock)
    assert await provider.token() == "tok1"
    provider.invalidate("tok1")
    assert await provider.token() == "tok2"
    provider.invalidate("tok1")  # chamada concorrente com o token já trocado: no-op
    assert await provider.token() == "tok2"
    assert server.calls == 2
