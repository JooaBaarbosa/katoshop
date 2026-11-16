from pydantic_settings import SettingsConfigDict

from ks_platform.settings import BaseServiceSettings


class CartSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="CART_")

    service_name: str = "cart"
    jwks_url: str = "http://identity:8000/.well-known/jwks.json"
    # Sem banco relacional: BaseServiceSettings exige o campo, então fica um valor inerte.
    database_url: str = "unused://"
    redis_url: str = "redis://redis:6379/0"
    amqp_url: str | None = None
    catalog_url: str = "http://catalog:8000"
    promotions_url: str = "http://promotions:8000"
    identity_token_url: str = "http://identity:8000/v1/auth/service-token"  # noqa: S105
    client_id: str = "cart"
    client_secret: str
    guest_ttl_s: int = 2592000
    max_lines: int = 50
    max_qty: int = 20
