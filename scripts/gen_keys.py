"""Gera a chave de assinatura Ed25519 do identity e prepara o .env local.

Uso (na raiz do repositório): uv run python scripts/gen_keys.py [--force]
"""

import argparse
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = Path(__file__).resolve().parent.parent
KEY_RELATIVE_PATH = Path("infra") / "secrets" / "identity-signing-key.pem"
# O compose monta a chave como secret de arquivo (bind mount): o container vê o dono e o
# modo do host. O identity roda como usuário sem privilégio (uid 10001), que no Linux não é
# o dono do arquivo; com 0600 ele não consegue ler. Por isso o arquivo fica 0644 e quem
# protege a chave no host é a pasta infra/secrets/ (0700, fora do git).
KEY_MODE = 0o644
SECRETS_DIR_MODE = 0o700


def main(argv: Sequence[str] | None = None, root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="sobrescreve a chave existente")
    args = parser.parse_args(argv)

    key_path = root / KEY_RELATIVE_PATH
    if key_path.exists() and not args.force:
        print(f"Chave já existe em {key_path}; use --force para sobrescrever.")
    else:
        key_path.parent.mkdir(parents=True, exist_ok=True)
        pem = Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        key_path.write_bytes(pem)
        print(f"Chave gerada em {key_path}")
    key_path.parent.chmod(SECRETS_DIR_MODE)
    key_path.chmod(KEY_MODE)

    env_path = root / ".env"
    example_path = root / ".env.example"
    if not env_path.exists() and example_path.exists():
        shutil.copyfile(example_path, env_path)
        print(f"Criado {env_path} a partir de .env.example")
    return 0


if __name__ == "__main__":
    sys.exit(main())
