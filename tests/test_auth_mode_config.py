"""The startup guard on the authentication kill switch.

The lifespan never runs in the test suite — `ASGITransport` is used without a
`LifespanManager` — so `validate_auth_settings` is called directly here. Without
this file the guard would be the one piece of the feature nothing exercises,
which is precisely the piece whose failure is unrecoverable.
"""

from collections.abc import Iterator

import pytest

from app.core.auth_mode import AuthConfigurationError, auth_disabled, validate_auth_settings
from app.core.config import AppEnv, AuthMode, settings


@pytest.fixture
def auth_settings() -> Iterator[None]:
    """`settings` is a process-wide singleton — a test that leaves the switch on
    would turn authentication off for every test after it."""
    saved = (settings.security.auth_mode, settings.security.dev_user_id, settings.env)
    yield
    settings.security.auth_mode, settings.security.dev_user_id, settings.env = saved


def test_enforced_needs_nothing(auth_settings: None) -> None:
    settings.security.auth_mode = AuthMode.ENFORCED
    settings.security.dev_user_id = None
    settings.env = AppEnv.PRODUCTION

    validate_auth_settings()


def test_disabled_outside_local_refuses_to_start(auth_settings: None) -> None:
    """The guard that matters. A staging deploy with this on answers to anyone."""
    settings.security.auth_mode = AuthMode.DISABLED
    settings.security.dev_user_id = 1
    settings.env = AppEnv.STAGING

    with pytest.raises(AuthConfigurationError, match="requires ENV 'local'"):
        validate_auth_settings()


def test_disabled_in_production_refuses_to_start(auth_settings: None) -> None:
    settings.security.auth_mode = AuthMode.DISABLED
    settings.security.dev_user_id = 1
    settings.env = AppEnv.PRODUCTION

    with pytest.raises(AuthConfigurationError):
        validate_auth_settings()


def test_disabled_without_a_dev_user_refuses_to_start(auth_settings: None) -> None:
    """`user.id` is a foreign key, so a request that is nobody cannot write."""
    settings.security.auth_mode = AuthMode.DISABLED
    settings.security.dev_user_id = None
    settings.env = AppEnv.LOCAL

    with pytest.raises(AuthConfigurationError, match="DEV_USER_ID"):
        validate_auth_settings()


def test_disabled_locally_with_a_dev_user_is_allowed(
    auth_settings: None, caplog: pytest.LogCaptureFixture
) -> None:
    settings.security.auth_mode = AuthMode.DISABLED
    settings.security.dev_user_id = 7
    settings.env = AppEnv.LOCAL

    with caplog.at_level("WARNING", logger="app.auth"):
        validate_auth_settings()

    assert "AUTHENTICATION IS DISABLED" in caplog.text
    assert auth_disabled() is True


def test_the_switch_is_off_by_default() -> None:
    """A fresh checkout must enforce. This asserts the shipped default, not a fixture."""
    assert AuthMode("enforced") == AuthMode.ENFORCED
    assert settings.security.auth_mode is AuthMode.ENFORCED
