from pydantic import BaseModel, Field

from catalog.domain.images import STORAGE_KEY_RE

# Só caminhos internos: uma barra, sem "//" nem barra invertida (evita open redirect).
INTERNAL_PATH_RE = r"^/([^/\\][^\\]*)?$"


class Hero(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    subtitle: str = Field(min_length=1, max_length=200)
    cta_label: str = Field(min_length=1, max_length=30)
    cta_href: str = Field(pattern=INTERNAL_PATH_RE)
    image_key: str = Field(pattern=STORAGE_KEY_RE)


class Cta(BaseModel):
    label: str = Field(min_length=1, max_length=30)
    href: str = Field(pattern=INTERNAL_PATH_RE)


class Policies(BaseModel):
    shipping_text: str
    returns_text: str
    pix_discount_percent: int = Field(ge=0, le=20)
    max_installments: int = Field(ge=1, le=12)
    demo_notice: str


class StorefrontSettings(BaseModel):
    hero: Hero
    secondary_cta: Cta
    featured_collection_slugs: list[str] = Field(max_length=3)
    policies: Policies
