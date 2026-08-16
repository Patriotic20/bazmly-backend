"""The signature check on Telegram's `initData`.

This is the whole of the trust boundary for Mini App sign-in: whatever it
accepts becomes a signed-in user. It takes no session and no I/O, so it is
tested directly rather than through the API.

The payloads here are built by signing them the way Telegram does, not by
pasting a captured string — a fixture copied from a real session would be tied
to one bot token and would rot the moment it changed.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest

from app.core.exceptions import PermissionDeniedError, ValidationFailedError
from app.modules.auth.telegram import parse_init_data

BOT_TOKEN = "123456:test-bot-token"
MAX_AGE = 86_400

NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)


def sign(fields: dict[str, str], bot_token: str = BOT_TOKEN) -> str:
    """Build an `initData` string the way Telegram builds one."""
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def init_data(
    *,
    user: dict[str, object] | None = None,
    auth_date: datetime = NOW,
    bot_token: str = BOT_TOKEN,
    **extra: str,
) -> str:
    payload = {
        "user": json.dumps(user if user is not None else {"id": 42, "first_name": "Aziz"}),
        "auth_date": str(int(auth_date.timestamp())),
        "query_id": "AAH-test",
        **extra,
    }
    return sign(payload, bot_token)


def test_a_genuine_payload_yields_its_user() -> None:
    parsed = parse_init_data(
        init_data(user={"id": 42, "first_name": "Aziz", "last_name": "Umarov"}),
        BOT_TOKEN,
        NOW,
        MAX_AGE,
    )

    assert parsed.id == 42
    assert parsed.first_name == "Aziz"
    assert parsed.last_name == "Umarov"


def test_optional_fields_are_optional() -> None:
    """A Telegram account with no surname and no username is ordinary."""
    parsed = parse_init_data(
        init_data(user={"id": 7, "first_name": "Kamola"}), BOT_TOKEN, NOW, MAX_AGE
    )

    assert parsed.last_name is None
    assert parsed.username is None


def test_a_tampered_field_is_refused() -> None:
    """The attack this whole module exists to stop: editing the user id."""
    genuine = init_data(user={"id": 42, "first_name": "Aziz"})
    forged = genuine.replace("42", "1")

    with pytest.raises(PermissionDeniedError):
        parse_init_data(forged, BOT_TOKEN, NOW, MAX_AGE)


def test_a_payload_signed_with_another_token_is_refused() -> None:
    """Someone else's bot must not sign users into this one."""
    with pytest.raises(PermissionDeniedError):
        parse_init_data(init_data(bot_token="999:someone-elses-bot"), BOT_TOKEN, NOW, MAX_AGE)


def test_a_missing_hash_is_refused() -> None:
    with pytest.raises(PermissionDeniedError):
        parse_init_data("user=%7B%22id%22%3A1%7D&auth_date=100", BOT_TOKEN, NOW, MAX_AGE)


def test_an_extra_field_invalidates_the_signature() -> None:
    """Appending to a captured payload must not survive the check."""
    with pytest.raises(PermissionDeniedError):
        parse_init_data(init_data() + "&is_admin=true", BOT_TOKEN, NOW, MAX_AGE)


def test_a_stale_payload_is_refused() -> None:
    """The signature never expires, so `auth_date` is what bounds a replay."""
    yesterday = NOW - timedelta(seconds=MAX_AGE + 60)

    with pytest.raises(PermissionDeniedError):
        parse_init_data(init_data(auth_date=yesterday), BOT_TOKEN, NOW, MAX_AGE)


def test_a_payload_inside_the_window_is_accepted() -> None:
    recent = NOW - timedelta(seconds=MAX_AGE - 60)

    assert parse_init_data(init_data(auth_date=recent), BOT_TOKEN, NOW, MAX_AGE).id == 42


def test_an_unconfigured_bot_token_refuses_everything() -> None:
    """An empty key must not become a key that anyone can sign with."""
    with pytest.raises(ValidationFailedError):
        parse_init_data(init_data(), "", NOW, MAX_AGE)


def test_a_payload_without_a_user_is_refused() -> None:
    """Telegram omits `user` when the app is opened from an inline context."""
    signed = sign({"auth_date": str(int(NOW.timestamp())), "query_id": "AAH-test"})

    with pytest.raises(PermissionDeniedError):
        parse_init_data(signed, BOT_TOKEN, NOW, MAX_AGE)


def test_a_user_without_an_integer_id_is_refused() -> None:
    with pytest.raises(PermissionDeniedError):
        parse_init_data(init_data(user={"id": "42", "first_name": "Aziz"}), BOT_TOKEN, NOW, MAX_AGE)
