import hashlib
from typing import Literal

MAX_IMAGE_BYTES = 8 * 1024 * 1024
STORAGE_KEY_RE = r"^products/[0-9a-f]{64}\.(jpg|png|webp)$"

_PNG = b"\x89PNG\r\n\x1a\n"


def detect_image_type(head: bytes) -> Literal["jpg", "png", "webp"] | None:
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(_PNG):
        return "png"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def storage_key(data: bytes, ext: str) -> str:
    return f"products/{hashlib.sha256(data).hexdigest()}.{ext}"
