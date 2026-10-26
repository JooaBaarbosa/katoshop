from typing import Any

import httpx
import jwt
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import update

from identity.adapters.models import User
from identity.domain.lockout import MAX_FAILURES
from ks_platform.auth import Principal, require_audience

from .conftest import PASSWORD, STAFF_PASSWORD, register


def _claims(token: str) -> dict[str, Any]:
    return jwt.decode(token, options={"verify_signature": False})


async def test_register_login_me_flow(client: httpx.AsyncClient) -> None:
    registered = await register(client, "  Ana@Example.com ")
    assert registered["expires_in"] == 900
    user: Any = registered["user"]
    assert user["email"] == "ana@example.com"
    assert user["kind"] == "customer"

    login = await client.post(
        "/v1/auth/login", json={"email": "ANA@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200
    pair = login.json()
    assert set(pair) == {
        "access_token",
        "refresh_token",
        "expires_in",
        "refresh_expires_at",
        "user",
    }

    me = await client.get("/v1/me", headers={"Authorization": f"Bearer {pair['access_token']}"})
    assert me.status_code == 200
    assert me.json() == {
        "id": pair["user"]["id"],
        "email": "ana@example.com",
        "name": "Ana",
        "kind": "customer",
        "roles": [],
    }


async def test_register_duplicate_email_409(client: httpx.AsyncClient) -> None:
    await register(client)
    response = await client.post(
        "/v1/auth/register",
        json={"email": "ANA@example.com", "password": PASSWORD, "name": "Outra"},
    )
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "identity.auth.email_taken"


async def test_weak_password_422_field_errors(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/auth/register",
        json={"email": "joana@example.com", "password": "xjoanax1", "name": "Joana"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "identity.auth.weak_password"
    assert body["errors"] == {"body.password": ["too_short", "contains_email"]}


async def test_invalid_body_422(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/auth/register", json={"email": "nope", "password": PASSWORD, "name": ""}
    )
    assert response.status_code == 422
    assert set(response.json()["errors"]) == {"body.email", "body.name"}


async def test_login_responses_identical_for_unknown_wrong_and_locked(
    client: httpx.AsyncClient,
) -> None:
    await register(client, "ana@example.com")
    await register(client, "bia@example.com")
    for _ in range(MAX_FAILURES):
        await client.post(
            "/v1/auth/login", json={"email": "bia@example.com", "password": "errada-123"}
        )

    responses = [
        await client.post(
            "/v1/auth/login", json={"email": "ninguem@example.com", "password": PASSWORD}
        ),
        await client.post(
            "/v1/auth/login", json={"email": "ana@example.com", "password": "errada-123"}
        ),
        await client.post(
            "/v1/auth/login", json={"email": "bia@example.com", "password": PASSWORD}
        ),
    ]

    bodies = []
    for response in responses:
        assert response.status_code == 401
        body = response.json()
        body.pop("trace_id")
        bodies.append(body)
    assert bodies[0]["code"] == "identity.auth.invalid_credentials"
    assert bodies[0] == bodies[1] == bodies[2]
    assert len({r.headers["content-type"] for r in responses}) == 1


async def test_login_ignores_audience_in_body(client: httpx.AsyncClient) -> None:
    await register(client)
    response = await client.post(
        "/v1/auth/login",
        json={"email": "ana@example.com", "password": PASSWORD, "audience": "admin"},
    )
    assert response.status_code == 200
    assert _claims(response.json()["access_token"])["aud"] == "storefront"


async def test_staff_login_audience_admin(client: httpx.AsyncClient, app: FastAPI) -> None:
    await app.state.auth_service.create_staff("equipe@example.com", STAFF_PASSWORD, "Equipe")

    response = await client.post(
        "/v1/auth/staff/login", json={"email": "equipe@example.com", "password": STAFF_PASSWORD}
    )

    assert response.status_code == 200
    claims = _claims(response.json()["access_token"])
    assert claims["aud"] == "admin"
    assert claims["kind"] == "staff"
    assert claims["roles"] == ["admin"]
    assert response.json()["user"]["roles"] == ["admin"]
    # cliente não entra pelo login de staff, com a mesma resposta de credenciais inválidas
    await register(client)
    denied = await client.post(
        "/v1/auth/staff/login", json={"email": "ana@example.com", "password": PASSWORD}
    )
    assert denied.status_code == 401
    assert denied.json()["code"] == "identity.auth.invalid_credentials"


async def test_customer_token_forbidden_on_admin_only_route(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    @app.get("/test/admin-only")
    async def admin_only(
        _: Principal = Depends(require_audience("admin")),  # noqa: B008
    ) -> dict[str, bool]:
        return {"ok": True}

    pair = await register(client)

    # R1: assinatura válida em outra audiência é 403, não 401
    forbidden = await client.get(
        "/test/admin-only", headers={"Authorization": f"Bearer {pair['access_token']}"}
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "auth.forbidden"
    missing = await client.get("/test/admin-only")
    assert missing.status_code == 401
    assert missing.json()["code"] == "auth.missing_token"


async def test_me_accepts_admin_token_and_rejects_bad_ones(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await app.state.auth_service.create_staff("equipe@example.com", STAFF_PASSWORD, "Equipe")
    login = await client.post(
        "/v1/auth/staff/login", json={"email": "equipe@example.com", "password": STAFF_PASSWORD}
    )

    me = await client.get(
        "/v1/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["kind"] == "staff"

    assert (await client.get("/v1/me")).status_code == 401
    bad = await client.get("/v1/me", headers={"Authorization": "Bearer lixo"})
    assert bad.status_code == 401
    assert bad.json()["code"] == "auth.invalid_token"


async def test_refresh_rotates_and_logout_revokes(client: httpx.AsyncClient) -> None:
    first = await register(client)

    refreshed = await client.post(
        "/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert refreshed.status_code == 200
    second = refreshed.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert second["user"]["email"] == "ana@example.com"

    logout = await client.post("/v1/auth/logout", json={"refresh_token": second["refresh_token"]})
    assert logout.status_code == 204
    assert logout.content == b""
    after = await client.post("/v1/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert after.status_code == 401
    assert after.json()["code"] == "identity.auth.invalid_refresh"
    # logout com token desconhecido também é 204 (idempotente)
    again = await client.post("/v1/auth/logout", json={"refresh_token": "desconhecido"})
    assert again.status_code == 204


async def test_refresh_unknown_token_401(client: httpx.AsyncClient) -> None:
    response = await client.post("/v1/auth/refresh", json={"refresh_token": "nada"})
    assert response.status_code == 401
    assert response.json()["code"] == "identity.auth.invalid_refresh"


async def test_disabled_user_cannot_login_or_refresh(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    pair = await register(client)
    async with app.state.session_factory() as session, session.begin():
        await session.execute(update(User).values(status="disabled"))

    login = await client.post(
        "/v1/auth/login", json={"email": "ana@example.com", "password": PASSWORD}
    )
    assert login.status_code == 401
    assert login.json()["code"] == "identity.auth.invalid_credentials"
    refresh = await client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert refresh.status_code == 401
    assert refresh.json()["code"] == "identity.auth.invalid_refresh"


async def test_login_normalizes_padded_mixed_case_email(client: httpx.AsyncClient) -> None:
    await register(client, "ana@x.com")

    response = await client.post(
        "/v1/auth/login", json={"email": "  Ana@X.com ", "password": PASSWORD}
    )

    assert response.status_code == 200


async def test_localhost_email_register_login_and_staff_login(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    # R14: os endereços demo usam o domínio de uso especial katoshop.localhost
    registered = await register(client, "  Cliente@Katoshop.Localhost ")
    assert registered["user"]["email"] == "cliente@katoshop.localhost"  # type: ignore[index]
    login = await client.post(
        "/v1/auth/login", json={"email": "cliente@katoshop.localhost", "password": PASSWORD}
    )
    assert login.status_code == 200

    await app.state.auth_service.create_staff("equipe@katoshop.localhost", STAFF_PASSWORD, "Equipe")
    staff = await client.post(
        "/v1/auth/staff/login",
        json={"email": "Equipe@katoshop.localhost", "password": STAFF_PASSWORD},
    )
    assert staff.status_code == 200
    assert _claims(staff.json()["access_token"])["aud"] == "admin"


@pytest.mark.parametrize(
    "email", ["a@@katoshop.localhost", "sem-arroba.localhost", "a b@x.com", ""]
)
async def test_invalid_email_syntax_still_422(client: httpx.AsyncClient, email: str) -> None:
    for path in ("/v1/auth/register", "/v1/auth/login", "/v1/auth/staff/login"):
        response = await client.post(
            path, json={"email": email, "password": PASSWORD, "name": "Ana"}
        )
        assert response.status_code == 422, (path, response.text)
        assert set(response.json()["errors"]) == {"body.email"}
