"""Seed idempotente da loja demo: `python -m seed` (a partir de scripts/).

Carrega categorias, coleções, produtos, variantes, estoque inicial, fotos creditadas e a
configuração da vitrine pelas APIs de admin. Rodar de novo não cria nada repetido.
"""

import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from seed import data
from seed.client import CatalogAdmin, SeedError, staff_login

SEED_DIR = Path(__file__).resolve().parent
MANIFEST = SEED_DIR / "images.json"
CACHE_DIR = SEED_DIR / ".cache"
INITIAL_NOTE = "Estoque inicial do seed demo"


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise SeedError(f"variável de ambiente {name} não definida")
    return value


# ---------------------------------------------------------------------------- fotos


def load_manifest() -> list[dict[str, Any]]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def photo_bytes(http: httpx.Client, image: dict[str, Any]) -> bytes:
    """Bytes da foto: do cache se o hash bate, senão baixa e confere o sha256."""
    expected = image["sha256"]
    cached = CACHE_DIR / f"{expected}.jpg"
    if cached.is_file():
        data = cached.read_bytes()
        if hashlib.sha256(data).hexdigest() == expected:
            return data
    response = http.get(image["download_url"], follow_redirects=True, timeout=60)
    if response.status_code != 200:
        raise SeedError(
            f"download da foto {image['id']} falhou ({response.status_code}): "
            f"{image['download_url']}"
        )
    data = response.content
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise SeedError(
            f"sha256 divergente na foto {image['id']}: esperado {expected}, recebido {actual}. "
            f"O arquivo em {image['download_url']} mudou desde a curadoria; confira a foto e "
            "atualize images.json antes de rodar o seed de novo."
        )
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data


# ---------------------------------------------------------------------------- etapas


def seed_categories(api: CatalogAdmin, counts: Counter[str]) -> dict[str, str]:
    existing = {c["slug"]: c for c in api.categories()}
    ids: dict[str, str] = {}
    for category in data.CATEGORIES:
        wanted = {"name": category.name, "position": category.position}
        current = existing.get(category.slug)
        if current is None:
            current = api.create_category({"slug": category.slug, **wanted})
            counts["categorias criadas"] += 1
        elif any(current[k] != v for k, v in wanted.items()):
            current = api.update_category(current["id"], wanted)
            counts["categorias atualizadas"] += 1
        ids[category.slug] = current["id"]
    return ids


def seed_collections(api: CatalogAdmin, counts: Counter[str]) -> dict[str, str]:
    existing = {c["slug"]: c for c in api.collections()}
    ids: dict[str, str] = {}
    for collection in data.COLLECTIONS:
        wanted = {
            "name": collection.name,
            "description": collection.description,
            "featured": collection.featured,
            "position": collection.position,
        }
        current = existing.get(collection.slug)
        if current is None:
            current = api.create_collection({"slug": collection.slug, **wanted})
            counts["coleções criadas"] += 1
        elif any(current[k] != v for k, v in wanted.items()):
            current = api.update_collection(current["id"], wanted)
            counts["coleções atualizadas"] += 1
        ids[collection.slug] = current["id"]
    return ids


def _upsert_product(
    api: CatalogAdmin, product: data.Product, category_id: str, counts: Counter[str]
) -> dict[str, Any]:
    wanted: dict[str, Any] = {
        "name": product.name,
        "description": product.description,
        "category_id": category_id,
        "base_price_cents": product.base_price_cents,
        "attributes": product.attributes,
    }
    current = api.find_product(product.slug)
    if current is None:
        counts["produtos criados"] += 1
        return api.create_product({"slug": product.slug, **wanted})
    if any(current[k] != v for k, v in wanted.items()):
        counts["produtos atualizados"] += 1
        return api.update_product(current["id"], {"version": current["version"], **wanted})
    return current


def _seed_stock(
    api: CatalogAdmin,
    product: data.Product,
    before: set[str],
    variants: list[dict[str, Any]],
    counts: Counter[str],
) -> None:
    """Estoque inicial só em variante nova (ou que ficou sem nenhum movimento, caso uma
    execução anterior tenha parado entre gerar a variante e lançar o estoque)."""
    by_option = {(v["color_code"], v["size_code"]): v for v in variants}
    for color, quantities in product.stock.items():
        for size, quantity in zip(product.sizes, quantities, strict=True):
            variant = by_option[(color, size)]
            if quantity == 0:
                continue
            is_new = variant["id"] not in before
            if not is_new and (variant["stock_on_hand"] != 0 or api.has_movements(variant["id"])):
                continue
            api.adjust_stock(variant["id"], quantity, "initial", INITIAL_NOTE)
            counts["movimentos initial"] += 1


def _seed_images(
    api: CatalogAdmin,
    http: httpx.Client,
    product: data.Product,
    product_id: str,
    images: list[dict[str, Any]],
    counts: Counter[str],
) -> None:
    wanted_keys: set[str] = set()
    for image in images:
        if product.slug not in image["used_by"]:
            continue
        fields = {
            "alt": image["alt"],
            "credit_author": image["author"],
            "credit_source_url": image["source_url"],
            "license": image["license"],
        }
        if image.get("color_code"):
            fields["color_code"] = image["color_code"]
        created = api.upload_image(product_id, photo_bytes(http, image), fields)
        counts["fotos criadas" if created else "fotos já existentes"] += 1
        wanted_keys.add(f"products/{image['sha256']}.jpg")
    # Foto que saiu do manifesto sai também do produto (e de /creditos).
    for stale in api.product(product_id)["images"]:
        if stale["storage_key"] not in wanted_keys:
            api.delete_image(stale["id"])
            counts["fotos removidas"] += 1


def seed_products(
    api: CatalogAdmin,
    http: httpx.Client,
    category_ids: dict[str, str],
    images: list[dict[str, Any]],
    counts: Counter[str],
) -> dict[str, str]:
    ids: dict[str, str] = {}
    for product in data.PRODUCTS:
        current = _upsert_product(api, product, category_ids[product.category_slug], counts)
        product_id = current["id"]
        before = {v["id"] for v in current["variants"]}
        generated = api.generate_variants(product_id, list(product.colors), list(product.sizes))
        created = [v for v in generated["variants"] if v["id"] not in before]
        counts["variantes criadas"] += len(created)
        _seed_stock(api, product, before, generated["variants"], counts)
        _seed_images(api, http, product, product_id, images, counts)
        if generated["status"] != "active":
            api.publish(product_id)
            counts["produtos publicados"] += 1
        ids[product.slug] = product_id
    return ids


def seed_collection_products(
    api: CatalogAdmin, collection_ids: dict[str, str], product_ids: dict[str, str]
) -> None:
    for collection in data.COLLECTIONS:
        ordered = [product_ids[slug] for slug in collection.product_slugs]
        api.set_collection_products(collection_ids[collection.slug], ordered)


def seed_settings(api: CatalogAdmin, images: list[dict[str, Any]]) -> None:
    hero = next(i for i in images if i["id"] == data.HERO_IMAGE_ID)
    # Chave endereçada por conteúdo, igual à que o catálogo gravou no upload da foto.
    api.put_settings(data.storefront_settings(f"products/{hero['sha256']}.jpg"))


# ---------------------------------------------------------------------------- main


def run() -> None:
    api_url = _env("API_URL", "http://api.katoshop.localhost").rstrip("/")
    email = _env("SEED_ADMIN_EMAIL")
    password = _env("SEED_ADMIN_PASSWORD")
    images = load_manifest()
    counts: Counter[str] = Counter()
    with httpx.Client(timeout=30) as http:
        token = staff_login(http, api_url, email, password)
        api = CatalogAdmin(http, api_url, token)
        category_ids = seed_categories(api, counts)
        collection_ids = seed_collections(api, counts)
        product_ids = seed_products(api, http, category_ids, images, counts)
        seed_collection_products(api, collection_ids, product_ids)
        seed_settings(api, images)
        overview = api.overview()

    print("Seed concluído (dados demonstrativos).")
    for key in (
        "categorias criadas",
        "categorias atualizadas",
        "coleções criadas",
        "coleções atualizadas",
        "produtos criados",
        "produtos atualizados",
        "produtos publicados",
        "variantes criadas",
        "movimentos initial",
        "fotos criadas",
        "fotos já existentes",
        "fotos removidas",
    ):
        print(f"  {key}: {counts[key]}")
    status = overview["products_by_status"]
    print(
        f"  catálogo: {status['active']} ativos, {status['draft']} rascunhos, "
        f"{status['archived']} arquivados; {overview['out_of_stock_variants']} variantes "
        "sem estoque"
    )


def main() -> int:
    try:
        run()
    except SeedError as exc:
        print(f"seed: erro: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"seed: erro de rede: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
