"""Arquiva os produtos de teste que sobraram na loja local: `python -m seed.archive_test_data`.

Ruling R26: a limpeza usa a API de admin (os registros ficam arquivados no banco), nunca a
remoção de volumes. Casa slugs `*-teste-*` (testes manuais das tarefas) e `*-e2e-*` (produtos
criados pelo Playwright). Idempotente: sem produto de teste ativo, não faz nada (caso da CI,
que sobe com volumes vazios).
"""

import sys
from fnmatch import fnmatchcase

import httpx

from seed.__main__ import _env
from seed.client import CatalogAdmin, SeedError, staff_login

TEST_SLUG_PATTERNS = ("*-teste-*", "*-e2e-*")


def is_test_slug(slug: str) -> bool:
    return any(fnmatchcase(slug, pattern) for pattern in TEST_SLUG_PATTERNS)


def archive_test_products(api: CatalogAdmin) -> list[str]:
    """Arquiva os produtos ativos com slug de teste; devolve os slugs arquivados."""
    matches: list[dict[str, str]] = []
    cursor: str | None = None
    while True:
        page = api.products_page("active", cursor)
        matches += [item for item in page["items"] if is_test_slug(item["slug"])]
        cursor = page["next_cursor"]
        if not cursor:
            break
    # arquiva depois de listar tudo: arquivar no meio mudaria as páginas seguintes
    for item in matches:
        api.archive(item["id"])
    return [item["slug"] for item in matches]


def main() -> int:
    try:
        api_url = _env("API_URL", "http://api.katoshop.localhost").rstrip("/")
        email, password = _env("SEED_ADMIN_EMAIL"), _env("SEED_ADMIN_PASSWORD")
        with httpx.Client(timeout=30) as http:
            token = staff_login(http, api_url, email, password)
            archived = archive_test_products(CatalogAdmin(http, api_url, token))
    except SeedError as exc:
        print(f"archive_test_data: erro: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"archive_test_data: erro de rede: {exc}", file=sys.stderr)
        return 1
    print(f"Produtos de teste arquivados: {len(archived)}")
    for slug in archived:
        print(f"  {slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
