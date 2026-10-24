import pytest

from catalog.domain.slugs import slugify


def test_slugify_removes_accents_and_punctuation():
    assert slugify("Moletom Zip Heavy Básico!") == "moletom-zip-heavy-basico"


def test_slugify_collapses_separators():
    assert slugify("  Calça -- Cargo  ") == "calca-cargo"


@pytest.mark.parametrize("text", ["", "   ", "!!!"])
def test_slugify_empty_raises(text):
    with pytest.raises(ValueError):
        slugify(text)
