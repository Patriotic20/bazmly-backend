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
    """Who the browser is allowed to call this API from.

    `origins` is the one value that has to change per deployment. The frontend
    calls the API directly rather than through a proxy, so a wrong value here is
    the difference between a working page and a page where every request fails
    while `curl` keeps working — CORS is enforced by the browser, not the server.
    """

    origins: list[str] = ["*"]
    allow_credentials: bool = True
    allow_methods: list[str] = ["*"]
    allow_headers: list[str] = ["*"]
    # A response header is invisible to browser JavaScript until it is named
    # here. `X-Request-ID` is on every response and is what ties a user's bug
    # report to a server log line, so the client has to be able to read it.
    expose_headers: list[str] = ["X-Request-ID"]


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


class TelegramConfig(BaseModel):
    """The bot the Mini App runs inside.

    `bot_token` is the only thing that can verify an `initData` payload: Telegram
    signs it with a key derived from the token, so without it the app cannot tell
    a real Telegram user from a forged query string. Empty means the Telegram
    sign-in route is switched off and answers 422 rather than trusting anything.

    `init_data_max_age_seconds` bounds a replay. The signature stays valid
    forever, so `auth_date` is what stops a captured payload being reused
    tomorrow.
    """

    bot_token: str = ""
    init_data_max_age_seconds: int = 86_400
    # Shared with Telegram when the webhook is registered, and sent back on every
    # delivery. The webhook URL is guessable; without this anyone could post a
    # forged update and make the bot say anything to any chat.
    webhook_secret: str = ""
    # Where the bot's button sends people. A `web_app` button, so the Mini App
    # opens inside Telegram with initData rather than in a browser without it.
    app_url: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token)


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
    telegram: TelegramConfig = TelegramConfig()
    redis: RedisConfig = RedisConfig()


settings = Settings()
