from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

PASSWORD = "Correto-Cavalo-Bateria-9"  # noqa: S105 (senha de teste)
STAFF_PASSWORD = "Cobalto-Sereno-Mare-42"  # noqa: S105 (senha de teste)


@pytest.fixture(autouse=True)
async def clean_users(migrated_url: str) -> AsyncIterator[None]:
    engine = create_async_engine(migrated_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE users CASCADE"))
    await engine.dispose()
    yield


async def register(
    client: httpx.AsyncClient, email: str = "ana@example.com", password: str = PASSWORD
) -> dict[str, object]:
    response = await client.post(
        "/v1/auth/register", json={"email": email, "password": password, "name": "Ana"}
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body
