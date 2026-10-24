from pathlib import Path

from pydantic_settings import SettingsConfigDict

from ks_platform.settings import BaseServiceSettings


class CatalogSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="CATALOG_")

    service_name: str = "catalog"
    jwks_url: str = "http://identity:8000/.well-known/jwks.json"
    media_root: Path = Path("/data/media")
    public_base_url: str = "http://api.katoshop.localhost/catalog"
