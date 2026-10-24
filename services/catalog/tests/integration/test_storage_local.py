from pathlib import Path

import pytest

from catalog.adapters.storage_local import LocalImageStorage


def png_files(root: Path) -> list[Path]:
    return list(root.rglob("*.png"))


KEY = "products/" + "a" * 64 + ".png"


async def test_save_then_read_roundtrip(tmp_path: Path) -> None:
    storage = LocalImageStorage(tmp_path)
    await storage.save(KEY, b"conteudo")
    assert await storage.read(KEY) == b"conteudo"
    assert [p.name for p in (tmp_path / "products").iterdir()] == [Path(KEY).name]


async def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert await LocalImageStorage(tmp_path).read(KEY) is None


async def test_save_is_idempotent_and_leaves_no_temp_files(tmp_path: Path) -> None:
    storage = LocalImageStorage(tmp_path)
    await storage.save(KEY, b"x")
    await storage.save(KEY, b"x")
    assert len(list((tmp_path / "products").iterdir())) == 1


@pytest.mark.parametrize(
    "key",
    [
        "products/../../etc/passwd",
        "../products/" + "a" * 64 + ".png",
        "products/" + "a" * 64 + ".png/",
        "products/" + "A" * 64 + ".png",
        "products/" + "a" * 64 + ".gif",
        "/etc/passwd",
        "",
    ],
)
async def test_rejects_path_traversal_key(tmp_path: Path, key: str) -> None:
    storage = LocalImageStorage(tmp_path)
    with pytest.raises(ValueError, match="storage key"):
        await storage.save(key, b"x")
    with pytest.raises(ValueError, match="storage key"):
        await storage.read(key)
    assert not png_files(tmp_path)
