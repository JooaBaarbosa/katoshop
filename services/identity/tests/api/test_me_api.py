import httpx

from .conftest import PASSWORD, register

NEW_PASSWORD = "Nova-Senha-Forte-77"  # noqa: S105 (senha de teste)


def _auth(pair: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {pair['access_token']}"}


async def test_patch_me_name_needs_no_password(client: httpx.AsyncClient) -> None:
    pair = await register(client)

    response = await client.patch("/v1/me", json={"name": "Ana Maria"}, headers=_auth(pair))

    assert response.status_code == 200
    assert response.json()["name"] == "Ana Maria"
    assert (await client.get("/v1/me", headers=_auth(pair))).json()["name"] == "Ana Maria"


async def test_patch_me_password_requires_current(client: httpx.AsyncClient) -> None:
    pair = await register(client)

    missing = await client.patch("/v1/me", json={"new_password": NEW_PASSWORD}, headers=_auth(pair))
    assert missing.status_code == 422
    assert missing.json()["code"] == "identity.me.current_password_required"

    wrong = await client.patch(
        "/v1/me",
        json={"new_password": NEW_PASSWORD, "current_password": "errada-123"},
        headers=_auth(pair),
    )
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "identity.auth.invalid_credentials"

    weak = await client.patch(
        "/v1/me",
        json={"new_password": "curta", "current_password": PASSWORD},
        headers=_auth(pair),
    )
    assert weak.status_code == 422
    assert weak.json()["errors"] == {"body.new_password": ["too_short"]}

    ok = await client.patch(
        "/v1/me",
        json={"new_password": NEW_PASSWORD, "current_password": PASSWORD},
        headers=_auth(pair),
    )
    assert ok.status_code == 200
    old = await client.post(
        "/v1/auth/login", json={"email": "ana@example.com", "password": PASSWORD}
    )
    new = await client.post(
        "/v1/auth/login", json={"email": "ana@example.com", "password": NEW_PASSWORD}
    )
    assert (old.status_code, new.status_code) == (401, 200)


async def test_patch_me_email_requires_current_and_detects_conflict(
    client: httpx.AsyncClient,
) -> None:
    pair = await register(client)
    await register(client, "bia@example.com")

    missing = await client.patch("/v1/me", json={"email": "novo@example.com"}, headers=_auth(pair))
    assert missing.status_code == 422

    taken = await client.patch(
        "/v1/me",
        json={"email": "BIA@example.com", "current_password": PASSWORD},
        headers=_auth(pair),
    )
    assert taken.status_code == 409
    assert taken.json()["code"] == "identity.auth.email_taken"

    ok = await client.patch(
        "/v1/me",
        json={"email": "Novo@Example.com", "current_password": PASSWORD},
        headers=_auth(pair),
    )
    assert ok.status_code == 200
    assert ok.json()["email"] == "novo@example.com"
    login = await client.post(
        "/v1/auth/login", json={"email": "novo@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200


async def test_patch_me_requires_token(client: httpx.AsyncClient) -> None:
    response = await client.patch("/v1/me", json={"name": "X"})
    assert response.status_code == 401
