import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "gen_keys.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_keys", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / ".env.example").write_text("POSTGRES_USER=katoshop\n", encoding="utf-8")
    return tmp_path


def test_generates_pkcs8_key_and_env(root: Path) -> None:
    assert _load().main([], root=root) == 0

    pem = root / "infra" / "secrets" / "identity-signing-key.pem"
    data = pem.read_bytes()
    assert data.startswith(b"-----BEGIN PRIVATE KEY-----")
    assert isinstance(load_pem_private_key(data, password=None), Ed25519PrivateKey)
    assert (root / ".env").read_text(encoding="utf-8") == "POSTGRES_USER=katoshop\n"


def test_does_not_overwrite_key_or_env_without_force(root: Path) -> None:
    gen = _load()
    gen.main([], root=root)
    pem = root / "infra" / "secrets" / "identity-signing-key.pem"
    first = pem.read_bytes()
    (root / ".env").write_text("CUSTOM=1\n", encoding="utf-8")

    assert gen.main([], root=root) == 0

    assert pem.read_bytes() == first
    assert (root / ".env").read_text(encoding="utf-8") == "CUSTOM=1\n"


def test_force_regenerates_key_but_keeps_env(root: Path) -> None:
    gen = _load()
    gen.main([], root=root)
    pem = root / "infra" / "secrets" / "identity-signing-key.pem"
    first = pem.read_bytes()
    (root / ".env").write_text("CUSTOM=1\n", encoding="utf-8")

    assert gen.main(["--force"], root=root) == 0

    assert pem.read_bytes() != first
    assert (root / ".env").read_text(encoding="utf-8") == "CUSTOM=1\n"
