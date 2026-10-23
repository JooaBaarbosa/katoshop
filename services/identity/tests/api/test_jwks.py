import httpx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import select

from identity.adapters.models import SigningKey as SigningKeyRow
from identity.adapters.signing import load_signing_key
from identity.settings import IdentitySettings


async def test_jwks_endpoint_serves_active_key(
    client: httpx.AsyncClient, settings: IdentitySettings
) -> None:
    response = await client.get("/.well-known/jwks.json")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    keys = response.json()["keys"]
    assert len(keys) == 1
    assert keys[0]["kid"] == load_signing_key(settings.signing_key_path).kid
    assert "d" not in keys[0]


async def test_startup_upserts_signing_key_row_idempotently(
    client: httpx.AsyncClient, app: FastAPI, settings: IdentitySettings
) -> None:
    kid = load_signing_key(settings.signing_key_path).kid
    # segundo startup com a mesma chave: não falha nem duplica
    async with LifespanManager(app):
        pass

    async with app.state.session_factory() as session:
        rows = (await session.scalars(select(SigningKeyRow).where(SigningKeyRow.kid == kid))).all()

    assert len(rows) == 1
    assert rows[0].active is True
    assert rows[0].private_key_ref == str(settings.signing_key_path)
    assert rows[0].public_jwk["kid"] == kid
    assert "d" not in rows[0].public_jwk
