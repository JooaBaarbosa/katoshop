import re
import unicodedata


def slugify(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in folded if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if not slug:
        raise ValueError("texto não gera slug")
    return slug
