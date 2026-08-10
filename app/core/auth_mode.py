"""The authentication kill switch, and the guard that keeps it out of production.

`AUTH_MODE=disabled` exists so the API can be driven from a browser or a frontend
before a login flow is wired up. It is not a convenience — it is the single most
dangerous setting in the system, because unlike a broken database or a missing
token it leaves every dashboard green while the API answers to anyone.

So the check here is fatal rather than a warning, and it runs in the lifespan
before the first request: a deploy that ships with the switch on must fail to
start, loudly, rather than serve.

Everything that consults the switch imports `auth_disabled` from here rather than
reading `settings` directly, so there is one place to grep and one place to change.
"""

import logging

from app.core.config import AppEnv, AuthMode, settings

logger = logging.getLogger("app.auth")


class AuthConfigurationError(RuntimeError):
    """Raised at startup. Deliberately fatal — see the module docstring."""


def validate_auth_settings() -> None:
    """Two checks, both fatal. Called from the lifespan."""
    if settings.security.auth_mode is AuthMode.ENFORCED:
        return

    # 1. The switch outside a developer's own machine. There is no legitimate
    #    reason for it, and the failure mode is total: no authentication, no
    #    permission checks, no ownership boundary at the guard layer.
    if settings.env is not AppEnv.LOCAL:
        raise AuthConfigurationError(
            f"AUTH_MODE 'disabled' requires ENV 'local', got '{settings.env}'. "
            "Refusing to start rather than serve an API that answers to anyone."
        )

    # 2. No identity to serve as. `user.id` is a foreign key on bookings, orders,
    #    messages and favourites, so a request that is nobody cannot write anything —
    #    the switch would appear to work and then fail on the first POST.
    if settings.security.dev_user_id is None:
        raise AuthConfigurationError(
            "AUTH_MODE 'disabled' needs SECURITY__DEV_USER_ID. Every request still "
            "has to be somebody, because `user.id` is a foreign key."
        )

    logger.warning(
        "=" * 72 + "\nAUTHENTICATION IS DISABLED. Every request is served as user %s.\n"
        "No token is required and no permission is checked, at any layer.\n" + "=" * 72,
        settings.security.dev_user_id,
    )


def auth_disabled() -> bool:
    """The one question the rest of the code asks.

    A function rather than a module-level constant so a test can flip the setting
    and have it take effect, the way `settings.sms.mode` already works.
    """
    return settings.security.auth_mode is AuthMode.DISABLED


def dev_user_id() -> int:
    """Only valid while `auth_disabled()` — `validate_auth_settings` proved it is set."""
    user_id = settings.security.dev_user_id
    if user_id is None:  # pragma: no cover - the startup guard makes this unreachable
        raise AuthConfigurationError("AUTH_MODE 'disabled' without SECURITY__DEV_USER_ID")
    return user_id
