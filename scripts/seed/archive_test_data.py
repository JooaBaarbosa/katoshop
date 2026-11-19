"""Arquiva os dados de teste que sobraram na loja local: `python -m seed.archive_test_data`.

Ruling R26: a limpeza usa as APIs de admin (os registros ficam no banco), nunca a remoção de
volumes. Produtos: arquiva os slugs `*-teste-*` (testes manuais das tarefas) e `*-e2e-*`
(criados pelo Playwright). Cupons: desativa os códigos `E2E-*` (criados pelo Playwright).
Idempotente: sem dado de teste ativo, não faz nada (caso da CI, que sobe com volumes vazios).
"""

import sys
from fnmatch import fnmatchcase

import httpx

from seed.__main__ import _env
from seed.client import CatalogAdmin, PromotionsAdmin, SeedError, staff_login

TEST_SLUG_PATTERNS = ("*-teste-*", "*-e2e-*")
TEST_COUPON_PREFIX = "E2E-"


def is_test_slug(slug: str) -> bool:
    return any(fnmatchcase(slug, pattern) for pattern in TEST_SLUG_PATTERNS)


def is_test_coupon(code: str) -> bool:
    return code.startswith(TEST_COUPON_PREFIX)


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


def deactivate_test_coupons(api: PromotionsAdmin) -> list[str]:
    """Desativa os cupons ativos com código `E2E-*`; devolve os códigos desativados."""
    matches: list[dict[str, str]] = []
    cursor: str | None = None
    while True:
        # a busca casa trecho do código ou da descrição; o prefixo é conferido aqui
        page = api.coupons_page(TEST_COUPON_PREFIX, active=True, cursor=cursor)
        matches += [item for item in page["items"] if is_test_coupon(item["code"])]
        cursor = page["next_cursor"]
        if not cursor:
            break
    # desativa depois de listar tudo: a lista filtra por ativo e mudaria as páginas seguintes
    for item in matches:
        api.deactivate(item["id"])
    return [item["code"] for item in matches]


def main() -> int:
    try:
        api_url = _env("API_URL", "http://api.katoshop.localhost").rstrip("/")
        email, password = _env("SEED_ADMIN_EMAIL"), _env("SEED_ADMIN_PASSWORD")
        with httpx.Client(timeout=30) as http:
            token = staff_login(http, api_url, email, password)
            archived = archive_test_products(CatalogAdmin(http, api_url, token))
            deactivated = deactivate_test_coupons(PromotionsAdmin(http, api_url, token))
    except SeedError as exc:
        print(f"archive_test_data: erro: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"archive_test_data: erro de rede: {exc}", file=sys.stderr)
        return 1
    print(f"Produtos de teste arquivados: {len(archived)}")
    for slug in archived:
        print(f"  {slug}")
    print(f"Cupons de teste desativados: {len(deactivated)}")
    for code in deactivated:
        print(f"  {code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
