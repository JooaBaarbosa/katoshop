from pydantic_settings import BaseSettings


class BaseServiceSettings(BaseSettings):
    """Base de configuração; cada serviço define o prefixo de env em `model_config`."""

    service_name: str
    database_url: str
    jwks_url: str
    otel_endpoint: str | None = None
    log_level: str = "INFO"
