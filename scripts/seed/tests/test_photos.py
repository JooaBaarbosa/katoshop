"""Download das fotos: cache por hash e erro claro quando o arquivo mudou na origem."""

import hashlib
import io
from collections import Counter
from pathlib import Path

import httpx
import pytest
from PIL import Image

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


def _jpeg(width: int, height: int, color: int = 0) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (color, color, color)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _image_for(pinned: bytes, width: int, height: int) -> dict[str, object]:
    return {**IMAGE, "sha256": hashlib.sha256(pinned).hexdigest(), "width": width, "height": height}


def test_rehashed_jpeg_with_same_dimensions_is_accepted_with_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(seed_main, "CACHE_DIR", tmp_path)
    new = _jpeg(32, 48, color=10)
    image = _image_for(_jpeg(32, 48, color=200), 32, 48)
    new_sha = hashlib.sha256(new).hexdigest()
    calls: list[str] = []
    with _client(new, calls) as http:
        assert seed_main.photo_bytes(http, image) == new
    err = capsys.readouterr().err
    assert (
        f"seed: aviso: bytes da foto unsplash-teste mudaram na CDN (sha256 {new_sha}), "
        "mesma imagem 32x48; usando a versão atual"
    ) in err
    assert (tmp_path / f"{image['sha256']}.jpg").read_bytes() == new
    # segunda chamada: cache aceito pela checagem de dimensões, sem novo download
    with _client(new, calls) as http:
        assert seed_main.photo_bytes(http, image) == new
    assert len(calls) == 1


def test_rehashed_jpeg_with_other_dimensions_aborts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(seed_main, "CACHE_DIR", tmp_path)
    image = _image_for(_jpeg(32, 48, color=200), 32, 48)
    with _client(_jpeg(40, 48), []) as http, pytest.raises(SeedError, match="sha256 divergente"):
        seed_main.photo_bytes(http, image)
    assert not list(tmp_path.iterdir())


def test_rehashed_non_jpeg_aborts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_main, "CACHE_DIR", tmp_path)
    buffer = io.BytesIO()
    Image.new("RGB", (32, 48)).save(buffer, format="PNG")
    image = _image_for(_jpeg(32, 48, color=200), 32, 48)
    with (
        _client(buffer.getvalue(), []) as http,
        pytest.raises(SeedError, match="sha256 divergente"),
    ):
        seed_main.photo_bytes(http, image)
    assert not list(tmp_path.iterdir())


class _FakeApi:
    """Imita o admin: a chave de storage de cada foto é o sha256 dos bytes enviados."""

    def __init__(self) -> None:
        self.images: list[dict[str, str]] = []
        self.deleted: list[str] = []
        self.settings: dict[str, object] = {}

    def upload_image(self, product_id: str, data: bytes, fields: dict[str, str]) -> bool:
        key = f"products/{hashlib.sha256(data).hexdigest()}.jpg"
        self.images.append({"id": key, "storage_key": key})
        return True

    def product(self, product_id: str) -> dict[str, object]:
        return {"images": list(self.images)}

    def delete_image(self, image_id: str) -> None:
        self.deleted.append(image_id)

    def put_settings(self, settings: dict[str, object]) -> None:
        self.settings = settings


def test_reencoded_photo_is_not_removed_as_stale_and_hero_uses_real_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(seed_main, "CACHE_DIR", tmp_path)
    new = _jpeg(32, 48, color=10)
    image = {
        **_image_for(_jpeg(32, 48, color=200), 32, 48),
        "alt": "a",
        "author": "b",
        "source_url": "https://unsplash.com/photos/x",
        "license": "Unsplash License",
        "used_by": ["camiseta"],
    }
    real_key = f"products/{hashlib.sha256(new).hexdigest()}.jpg"
    api = _FakeApi()
    product = type("P", (), {"slug": "camiseta"})()
    with _client(new, []) as http:
        counts: Counter[str] = Counter()
        seed_main._seed_images(api, http, product, "pid", [image], counts)  # type: ignore[arg-type]
        assert api.deleted == []
        monkeypatch.setattr(seed_main.data, "HERO_IMAGE_ID", image["id"])
        seed_main.seed_settings(api, http, [image])  # type: ignore[arg-type]
    assert api.settings["hero"]["image_key"] == real_key  # type: ignore[index]
