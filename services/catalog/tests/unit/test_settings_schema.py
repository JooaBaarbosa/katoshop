import pytest
from pydantic import ValidationError

from catalog.domain.settings_schema import StorefrontSettings

KEY = "products/" + "a" * 64 + ".jpg"


def _valid() -> dict:
    return {
        "hero": {
            "title": "Básicos pesados",
            "subtitle": "Moletons e camisetas de gramatura alta.",
            "cta_label": "Ver coleção",
            "cta_href": "/produtos",
            "image_key": KEY,
        },
        "secondary_cta": {"label": "Novidades", "href": "/novidades"},
        "featured_collection_slugs": ["moletons"],
        "policies": {
            "shipping_text": "Envio simulado.",
            "returns_text": "Troca em 7 dias.",
            "pix_discount_percent": 5,
            "max_installments": 6,
            "demo_notice": "Loja demonstrativa, nenhuma compra é real",
        },
    }


def test_valid_settings():
    assert StorefrontSettings.model_validate(_valid()).policies.max_installments == 6


def test_rejects_external_cta_href():
    d = _valid()
    d["hero"]["cta_href"] = "https://x"
    with pytest.raises(ValidationError):
        StorefrontSettings.model_validate(d)


def test_rejects_big_pix_discount():
    d = _valid()
    d["policies"]["pix_discount_percent"] = 50
    with pytest.raises(ValidationError):
        StorefrontSettings.model_validate(d)


def test_rejects_bad_image_key_and_too_many_collections():
    d = _valid()
    d["hero"]["image_key"] = "../etc/passwd"
    with pytest.raises(ValidationError):
        StorefrontSettings.model_validate(d)
    d = _valid()
    d["featured_collection_slugs"] = ["a", "b", "c", "d"]
    with pytest.raises(ValidationError):
        StorefrontSettings.model_validate(d)


@pytest.mark.parametrize("bad", ["//evil.com/x", "/\\evil.com", "/a\\b", "https://x", "x"])
@pytest.mark.parametrize("field", ["hero", "secondary_cta"])
def test_rejects_non_internal_hrefs(field, bad):
    d = _valid()
    d[field]["cta_href" if field == "hero" else "href"] = bad
    with pytest.raises(ValidationError):
        StorefrontSettings.model_validate(d)


@pytest.mark.parametrize("good", ["/", "/busca", "/colecoes/drop-inverno-26"])
@pytest.mark.parametrize("field", ["hero", "secondary_cta"])
def test_accepts_internal_hrefs(field, good):
    d = _valid()
    d[field]["cta_href" if field == "hero" else "href"] = good
    StorefrontSettings.model_validate(d)
