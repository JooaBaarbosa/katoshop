import httpx
import pytest
from asgi_lifespan import LifespanManager

from identity.main import create_app
from identity.settings import IdentitySettings

BOOTSTRAP_PASSWORD = "Raiz-Segura-Mare-42"  # noqa: S105 (senha de teste)


async def test_bootstrap_admin_created_on_startup_and_can_login(
    settings: IdentitySettings,
) -> None:
    settings = settings.model_copy(
        update={
            "bootstrap_admin_email": "Root@Example.com",
            "bootstrap_admin_password": BOOTSTRAP_PASSWORD,
        }
    )
    app = create_app(settings)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/auth/staff/login",
                json={"email": "root@example.com", "password": BOOTSTRAP_PASSWORD},
            )
    assert response.status_code == 200
    assert response.json()["user"]["roles"] == ["admin"]


async def test_bootstrap_weak_password_fails_startup(settings: IdentitySettings) -> None:
    settings = settings.model_copy(
        update={"bootstrap_admin_email": "root@example.com", "bootstrap_admin_password": "123"}
    )
    app = create_app(settings)

    with pytest.raises(RuntimeError, match=r"IDENTITY_BOOTSTRAP_ADMIN_PASSWORD.*too_short"):
        async with LifespanManager(app):
            pass
