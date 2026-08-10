from enum import StrEnum

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


class GoogleSettings(BaseModel):
    """Google Sign-In.

    `client_ids` is a list because iOS, Android and web each get their own OAuth
    client from Google and every one of them mints tokens with its own `aud`. An
    empty list means Google sign-in is off — unlike the auth kill switch this is
    not fatal at startup, since an app can ship perfectly well with phone login
    only. The endpoint refuses instead.
    """

    client_ids: list[str] = []
    jwks_url: str = "https://www.googleapis.com/oauth2/v3/certs"
    timeout_seconds: float = 5.0
    jwks_cache_seconds: int = 60 * 60

    @property
    def enabled(self) -> bool:
        return bool(self.client_ids)


class RedisConfig(BaseModel):
    url: str = "redis://localhost:6379/0"


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

    env: AppEnv = AppEnv.LOCAL
    database: DatabaseConfig
    run: RunConfig = RunConfig()
    api: ApiPrefix = ApiPrefix()
    cors: CorsConfig = CorsConfig()
    logging: LoggingConfig = LoggingConfig()
    security: SecurityConfig = SecurityConfig()
    google: GoogleSettings = GoogleSettings()
    redis: RedisConfig = RedisConfig()


settings = Settings()
