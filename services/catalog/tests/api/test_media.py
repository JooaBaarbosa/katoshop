import httpx
import pytest

from catalog.adapters.storage_local import LocalImageStorage
from catalog.settings import CatalogSettings

KEY = "products/" + "b" * 64 + ".webp"


async def test_media_served_with_immutable_cache(
    client: httpx.AsyncClient, settings: CatalogSettings
) -> None:
    await LocalImageStorage(settings.media_root).save(KEY, b"RIFFxxxxWEBPdata")
    response = await client.get(f"/v1/media/{KEY}")  # sem autenticação
    assert response.status_code == 200
    assert response.content == b"RIFFxxxxWEBPdata"
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_media_unknown_key_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/v1/media/{KEY}")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "key",
    [
        "products/../../etc/passwd",
        "products/%2e%2e/%2e%2e/etc/passwd",
        "products/short.png",
        "other/" + "b" * 64 + ".png",
        "products/" + "b" * 64 + ".gif",
    ],
)
async def test_media_invalid_key_404_without_touching_disk(
    client: httpx.AsyncClient, settings: CatalogSettings, key: str
) -> None:
    response = await client.get(f"/v1/media/{key}")
    assert response.status_code == 404
    assert not settings.media_root.exists()
