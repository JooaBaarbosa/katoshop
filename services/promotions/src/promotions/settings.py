from pydantic_settings import SettingsConfigDict

from ks_platform.settings import BaseServiceSettings


class PromotionsSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="PROMOTIONS_")

    service_name: str = "promotions"
    jwks_url: str = "http://identity:8000/.well-known/jwks.json"
