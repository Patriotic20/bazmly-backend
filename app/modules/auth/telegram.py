"""Verifying the `initData` a Telegram Mini App hands its own backend.

Telegram opens the web app with a query string describing the current user and
signs it. The signature is the only thing standing between "this is user
123456" and "someone typed `user_id=123456` into a URL", so this module is
pure verification with no I/O: it either returns a user Telegram vouched for, or
it raises.

The scheme, from Telegram's own documentation:

    secret_key       = HMAC_SHA256(key="WebAppData", message=bot_token)
    data_check_string= every field except `hash`, as "key=value",
                       sorted by key, joined with "\\n"
    expected         = HMAC_SHA256(key=secret_key, message=data_check_string)

Note the inversion in the first step — the literal string `WebAppData` is the
*key* and the bot token is the *message*, not the other way round. Getting that
backwards produces a validator that rejects every genuine payload, which reads
like a Telegram problem rather than a bug here.
"""

import hashlib
import hmac
import json
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl

from pydantic import BaseModel

from app.core.exceptions import PermissionDeniedError, ValidationFailedError

WEB_APP_DATA_KEY = b"WebAppData"

# Telegram sends `auth_date` as a Unix timestamp in seconds.
_SECONDS = 1


class TelegramUser(BaseModel):
    """The `user` object out of a verified `initData`, and nothing more.

    Telegram guarantees `id` and `first_name`. Everything else is optional —
    a user with no surname and no username is ordinary, not an error.
    """

    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    photo_url: str | None = None


def parse_init_data(
    init_data: str,
    bot_token: str,
    now: datetime,
    max_age_seconds: int,
) -> TelegramUser:
    """Return the user Telegram signed for, or raise.

    `now` is passed in rather than read here so the freshness window is testable
    without freezing the clock.
    """
    if not bot_token:
        # Refusing loudly beats validating against an empty key, which would
        # accept a payload signed with an empty key by anyone who guessed that.
        raise ValidationFailedError(
            "Telegram orqali kirish sozlanmagan",
            details={"reason": "bot_token_missing"},
        )

    fields = dict(parse_qsl(init_data, keep_blank_values=True))

    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise PermissionDeniedError("Telegram ma'lumotlari yaroqsiz")

    if not _signature_matches(fields, received_hash, bot_token):
        raise PermissionDeniedError("Telegram ma'lumotlari yaroqsiz")

    _require_fresh(fields.get("auth_date"), now, max_age_seconds)

    return _extract_user(fields.get("user"))


def _signature_matches(fields: dict[str, str], received_hash: str, bot_token: str) -> bool:
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(WEB_APP_DATA_KEY, bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    # Constant-time: a timing difference would leak the signature prefix by prefix.
    return hmac.compare_digest(expected, received_hash)


def _require_fresh(auth_date: str | None, now: datetime, max_age_seconds: int) -> None:
    """A valid signature never expires, so the timestamp is what bounds a replay."""
    if auth_date is None:
        raise PermissionDeniedError("Telegram ma'lumotlari yaroqsiz")

    try:
        issued_at = int(auth_date)
    except ValueError as error:
        raise PermissionDeniedError("Telegram ma'lumotlari yaroqsiz") from error

    age = int(now.timestamp()) - issued_at
    if age > max_age_seconds * _SECONDS:
        raise PermissionDeniedError("Telegram sessiyasi eskirgan. Ilovani qayta oching.")


def _extract_user(raw_user: str | None) -> TelegramUser:
    """`user` is a JSON object embedded in the query string as one value."""
    if not raw_user:
        raise PermissionDeniedError("Telegram ma'lumotlari yaroqsiz")

    try:
        payload: Any = json.loads(raw_user)
    except json.JSONDecodeError as error:
        raise PermissionDeniedError("Telegram ma'lumotlari yaroqsiz") from error

    if not isinstance(payload, dict):
        raise PermissionDeniedError("Telegram ma'lumotlari yaroqsiz")

    # The signature already proved Telegram wrote this, so a shape we cannot read
    # is our bug rather than an attack — but it still must not reach the database.
    if not isinstance(payload.get("id"), int) or not payload.get("first_name"):
        raise PermissionDeniedError("Telegram ma'lumotlari yaroqsiz")

    return TelegramUser.model_validate(payload)
