import hashlib
import re

from catalog.domain.images import MAX_IMAGE_BYTES, STORAGE_KEY_RE, detect_image_type, storage_key


def test_detects_jpg():
    assert detect_image_type(b"\xff\xd8\xff\xe0" + b"\x00" * 8) == "jpg"


def test_detects_png():
    assert detect_image_type(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8) == "png"


def test_detects_webp():
    assert detect_image_type(b"RIFF\x24\x00\x00\x00WEBPVP8 ") == "webp"


def test_rejects_riff_that_is_not_webp():
    assert detect_image_type(b"RIFF\x24\x00\x00\x00WAVEfmt ") is None


def test_rejects_pdf_and_short_input():
    assert detect_image_type(b"%PDF-1.7...") is None
    assert detect_image_type(b"") is None


def test_storage_key_matches_regex():
    data = b"abc"
    key = storage_key(data, "png")
    assert key == f"products/{hashlib.sha256(data).hexdigest()}.png"
    assert re.match(STORAGE_KEY_RE, key)
    assert not re.match(STORAGE_KEY_RE, "products/../x.png")


def test_max_bytes():
    assert MAX_IMAGE_BYTES == 8 * 1024 * 1024
