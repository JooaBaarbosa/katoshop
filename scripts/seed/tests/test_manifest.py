"""Invariantes do manifesto de fotos (images.json) e dos dados demo (data.py)."""

import json
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

from seed import data

SEED_DIR = Path(__file__).resolve().parents[1]
IMAGES = json.loads((SEED_DIR / "images.json").read_text(encoding="utf-8"))
LICENSES = {"Unsplash License", "Pexels License"}
DASHES = ("—", "–")
INTERNAL_PATH = re.compile(r"^/([^/\\\x00-\x20\x7f][^\\\x00-\x20\x7f]*)?$")


def _host_ok(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return any(host == d or host.endswith(f".{d}") for d in ("unsplash.com", "pexels.com"))


def test_every_product_has_at_least_one_image() -> None:
    used = {slug for image in IMAGES for slug in image["used_by"]}
    missing = [p.slug for p in data.PRODUCTS if p.slug not in used]
    assert missing == []


def test_images_only_reference_known_products_and_colors() -> None:
    products = {p.slug: p for p in data.PRODUCTS}
    for image in IMAGES:
        assert image["used_by"], image["id"]
        for slug in image["used_by"]:
            assert slug in products, (image["id"], slug)
            color = image.get("color_code")
            if color is not None:
                assert color in products[slug].colors, (image["id"], slug, color)


@pytest.mark.parametrize("image", IMAGES, ids=lambda image: image["id"])
def test_image_has_credit_license_and_hash(image: dict[str, object]) -> None:
    assert isinstance(image["author"], str) and image["author"].strip()
    assert isinstance(image["alt"], str) and image["alt"].strip()
    assert _host_ok(str(image["source_url"]))
    assert _host_ok(str(image["download_url"]))
    assert image["license"] in LICENSES
    assert re.fullmatch(r"[0-9a-f]{64}", str(image["sha256"]))


def test_image_ids_and_hashes_are_unique() -> None:
    assert len({i["id"] for i in IMAGES}) == len(IMAGES)
    assert len({i["sha256"] for i in IMAGES}) == len(IMAGES)


def test_hero_image_is_in_manifest() -> None:
    assert data.HERO_IMAGE_ID in {i["id"] for i in IMAGES}


def test_no_dashes_in_seed_texts() -> None:
    source = (SEED_DIR / "data.py").read_text(encoding="utf-8")
    manifest = (SEED_DIR / "images.json").read_text(encoding="utf-8")
    for dash in DASHES:
        assert dash not in source
        assert dash not in manifest


def test_catalog_shape() -> None:
    assert [c.name for c in data.CATEGORIES] == ["Camisetas", "Moletons", "Calças", "Acessórios"]
    assert [c.name for c in data.COLLECTIONS] == [
        "Drop Inverno 26",
        "Básicos pesados",
        "Rua à noite",
    ]
    assert 20 <= len(data.PRODUCTS) <= 28
    assert len({p.slug for p in data.PRODUCTS}) == len(data.PRODUCTS)
    categories = {c.slug for c in data.CATEGORIES}
    slugs = {p.slug for p in data.PRODUCTS}
    for product in data.PRODUCTS:
        assert product.category_slug in categories
        assert 6900 <= product.base_price_cents <= 42900
        assert set(product.attributes) == {"material", "gramatura", "modelagem", "cuidados"}
        assert set(product.stock) == set(product.colors)
        for quantities in product.stock.values():
            assert len(quantities) == len(product.sizes)
            assert all(q >= 0 for q in quantities)
    for collection in data.COLLECTIONS:
        assert collection.product_slugs
        assert set(collection.product_slugs) <= slugs


def test_stock_has_sold_out_sizes_and_products() -> None:
    zero_variants = sum(q == 0 for p in data.PRODUCTS for qs in p.stock.values() for q in qs)
    sold_out = [p for p in data.PRODUCTS if all(q == 0 for qs in p.stock.values() for q in qs)]
    assert zero_variants >= 6
    assert len(sold_out) >= 2


def test_r4_moletom_with_black_size_sold_out_and_others_in_stock() -> None:
    def qualifies(product: data.Product) -> bool:
        black = product.stock.get("PRT")
        return (
            product.category_slug == "moletons"
            and black is not None
            and 0 in black
            and any(q > 0 for q in black)
        )

    assert any(qualifies(p) for p in data.PRODUCTS)


def test_storefront_settings() -> None:
    hero = next(i for i in IMAGES if i["id"] == data.HERO_IMAGE_ID)
    key = f"products/{hero['sha256']}.jpg"
    s = data.storefront_settings(key)
    assert s["hero"]["image_key"] == key
    assert s["hero"]["title"] == "Streetwear para andar, não para guardar"
    assert s["hero"]["subtitle"] == "Camisetas, moletons e calças em tecido pesado, do P ao XGG"
    assert s["hero"]["cta_label"] == "Ver o drop atual"
    assert s["hero"]["cta_href"] == "/colecoes/drop-inverno-26"
    assert s["secondary_cta"] == {"label": "Todas as peças", "href": "/busca"}
    assert INTERNAL_PATH.fullmatch(s["hero"]["cta_href"])
    assert INTERNAL_PATH.fullmatch(s["secondary_cta"]["href"])
    policies = s["policies"]
    assert policies["pix_discount_percent"] == 5
    assert policies["max_installments"] == 3
    assert policies["demo_notice"] == "Loja demonstrativa, nenhuma compra é real"
    assert policies["shipping_text"] and policies["returns_text"]
    assert set(s["featured_collection_slugs"]) <= {c.slug for c in data.COLLECTIONS}
