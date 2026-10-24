"""Armazenamento de imagens em disco local: arquivos endereçados por conteúdo."""

import asyncio
import contextlib
import os
import re
import tempfile
from pathlib import Path

from catalog.domain.images import STORAGE_KEY_RE

_KEY = re.compile(STORAGE_KEY_RE)


class LocalImageStorage:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, key: str) -> Path:
        # fullmatch: o `$` do padrão aceitaria uma quebra de linha no fim; assim não aceita.
        if not _KEY.fullmatch(key):
            raise ValueError("invalid storage key")
        return self._root / key

    async def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        await asyncio.to_thread(_write_atomic, path, data)

    async def read(self, key: str) -> bytes | None:
        path = self._path(key)
        return await asyncio.to_thread(_read, path)


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Temporário na mesma pasta (mesmo volume) para o replace ser atômico.
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        Path(tmp_name).replace(path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            Path(tmp_name).unlink()
        raise


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError, IsADirectoryError, NotADirectoryError:
        return None
