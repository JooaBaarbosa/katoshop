"""Exporta o OpenAPI de cada serviço para packages/api-client/openapi/.

Uso (na raiz do repositório): uv run python scripts/export_openapi.py

Os apps são construídos com settings fictícias e sem rodar o lifespan, então nenhum banco é
necessário. O JSON sai determinístico (chaves ordenadas, LF) para o diff de contrato do CI.
"""

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI

from catalog.main import create_app as create_catalog_app
from catalog.settings import CatalogSettings
from identity.main import create_app as create_identity_app
from identity.settings import IdentitySettings

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "packages" / "api-client" / "openapi"
DUMMY_DATABASE_URL = "postgresql+asyncpg://openapi:openapi@localhost:5432/openapi"
DUMMY_JWKS_URL = "http://localhost:8000/.well-known/jwks.json"


def build_identity(workdir: Path) -> FastAPI:
    # o identity carrega a chave de assinatura ao criar o app: usa uma descartável
    key_path = workdir / "signing-key.pem"
    key_path.write_bytes(
        Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return create_identity_app(
        IdentitySettings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            database_url=DUMMY_DATABASE_URL,
            jwks_url=DUMMY_JWKS_URL,
            signing_key_path=key_path,
        )
    )


def build_catalog(workdir: Path) -> FastAPI:
    return create_catalog_app(
        CatalogSettings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            database_url=DUMMY_DATABASE_URL,
            jwks_url=DUMMY_JWKS_URL,
            media_root=workdir / "media",
        )
    )


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def main(output_dir: Path = OUTPUT_DIR) -> int:
    builders: dict[str, Callable[[Path], FastAPI]] = {
        "identity": build_identity,
        "catalog": build_catalog,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, build in builders.items():
            app = build(Path(tmp))
            target = output_dir / f"{name}.json"
            # newline="\n" evita CRLF no Windows
            with target.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(render(app.openapi()))
            print(f"OpenAPI de {name} gravado em {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
