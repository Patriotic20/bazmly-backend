from pydantic import BaseModel, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseModel):
    url: PostgresDsn
    echo: bool = False
    echo_pool: bool = False
    pool_size: int = 5
    max_overflow: int = 10


class RunConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False


class ApiPrefix(BaseModel):
    prefix: str = "/api"
    v1: str = "/v1"
    v2: str = "/v2"


class CorsConfig(BaseModel):
    origins: list[str] = ["*"]
    allow_credentials: bool = True
    allow_methods: list[str] = ["*"]
    allow_headers: list[str] = ["*"]


class SecurityConfig(BaseModel):
    """Signing material for access tokens.

    The default is a development placeholder and is rejected at startup in any
    non-local environment — a shared well-known secret is the same as no secret.
    """

    secret_key: str = "dev-only-change-me-32-bytes-min!!"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30


class WebhookConfig(BaseModel):
    """Shared secrets for provider callbacks. Empty means the provider is off."""

    payme_secret: str = ""
    click_secret: str = ""


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(request_id)s | %(message)s"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.template", ".env"),
        env_nested_delimiter="__",
        env_prefix="APP_CONFIG__",
        case_sensitive=False,
        extra="ignore",
    )

    database: DatabaseConfig
    run: RunConfig = RunConfig()
    api: ApiPrefix = ApiPrefix()
    cors: CorsConfig = CorsConfig()
    logging: LoggingConfig = LoggingConfig()
    security: SecurityConfig = SecurityConfig()
    webhooks: WebhookConfig = WebhookConfig()


settings = Settings()
