"""Download das fotos: cache por hash e erro claro quando o arquivo mudou na origem."""

import hashlib
from pathlib import Path

import httpx
import pytest

from seed import __main__ as seed_main
from seed.client import SeedError

PHOTO = b"\xff\xd8\xff fake jpeg bytes"
IMAGE = {
    "id": "unsplash-teste",
    "download_url": "https://images.unsplash.com/photo-teste?w=1600&q=80&fm=jpg",
    "sha256": hashlib.sha256(PHOTO).hexdigest(),
}


def _client(body: bytes, calls: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_downloads_once_then_uses_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_main, "CACHE_DIR", tmp_path)
    calls: list[str] = []
    with _client(PHOTO, calls) as http:
        assert seed_main.photo_bytes(http, IMAGE) == PHOTO
        assert seed_main.photo_bytes(http, IMAGE) == PHOTO
    assert calls == [IMAGE["download_url"]]
    assert (tmp_path / f"{IMAGE['sha256']}.jpg").read_bytes() == PHOTO


def test_hash_mismatch_aborts_with_clear_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(seed_main, "CACHE_DIR", tmp_path)
    with _client(b"outros bytes", []) as http, pytest.raises(SeedError) as excinfo:
        seed_main.photo_bytes(http, IMAGE)
    message = str(excinfo.value)
    assert "sha256 divergente" in message
    assert "unsplash-teste" in message
    assert not list(tmp_path.iterdir())
