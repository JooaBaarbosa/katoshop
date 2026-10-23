from pathlib import Path

from pydantic_settings import SettingsConfigDict

from ks_platform.settings import BaseServiceSettings


class IdentitySettings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="IDENTITY_")

    service_name: str = "identity"
    jwks_url: str = "http://identity:8000/.well-known/jwks.json"
    signing_key_path: Path
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    cookie_secure: bool = False
