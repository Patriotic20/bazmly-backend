from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py -> app/core -> app -> backend/
BACKEND_ROOT = Path(__file__).resolve().parents[2]


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


class AuthMode(StrEnum):
    """Whether the API checks who is calling.

    `disabled` exists for local work against a database whose login flow is not
    wired up yet. It is the most dangerous setting in the system — it turns off
    authentication *and* authorization, at every layer — so it is fatal outside
    `local` and the process refuses to start. See `app/core/auth_mode.py`.
    """

    ENFORCED = "enforced"
    DISABLED = "disabled"


class SecurityConfig(BaseModel):
    """Signing material for access tokens.

    The default is a development placeholder and is rejected at startup in any
    non-local environment — a shared well-known secret is the same as no secret.
    """

    secret_key: str = "dev-only-change-me-32-bytes-min!!"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    auth_mode: AuthMode = AuthMode.ENFORCED
    # Who every request is, when `auth_mode` is `disabled`. A real row rather than a
    # synthetic id: `user.id` is a foreign key on bookings, orders and messages, so
    # a made-up one turns "auth is off" into "every write fails on a constraint".
    dev_user_id: int | None = None


class AppEnv(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class RedisConfig(BaseModel):
    url: str = "redis://localhost:6379/0"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(request_id)s | %(message)s"


class Settings(BaseSettings):
    # The env files are addressed absolutely, not as `.env`. Relative paths
    # resolve against the working directory, which would mean the settings a
    # process gets depend on where it was launched from — and since `database.url`
    # has no default, launching from the repository root instead of `backend/`
    # would be a startup crash rather than a wrong value.
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env.template", BACKEND_ROOT / ".env"),
        env_nested_delimiter="__",
        env_prefix="APP_CONFIG__",
        case_sensitive=False,
        extra="ignore",
    )

    env: AppEnv = AppEnv.LOCAL
    database: DatabaseConfig
    run: RunConfig = RunConfig()
    api: ApiPrefix = ApiPrefix()
    cors: CorsConfig = CorsConfig()
    logging: LoggingConfig = LoggingConfig()
    security: SecurityConfig = SecurityConfig()
    redis: RedisConfig = RedisConfig()


settings = Settings()
