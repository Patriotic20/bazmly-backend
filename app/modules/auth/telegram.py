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

from pydantic import BaseModel, ValidationError

from app.core.exceptions import PermissionDeniedError, ValidationFailedError
from app.core.schemas import PhoneNumber

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
    photo_url: str | None = None


class TelegramContact(BaseModel):
    """The `contact` object out of a verified `requestContact` response.

    `user_id` matters as much as the number: it says whose contact this is, and
    the caller must check it against the account already signed in — otherwise a
    replayed payload would attach someone else's phone to the wrong person.
    """

    user_id: int
    # The same annotated type the rest of the API uses, so `998901234567` from
    # Telegram and `+998 90 123-45-67` from a form land in the database
    # identically — and a number outside Uzbekistan is refused here rather than
    # stored as something no one can call.
    phone_number: PhoneNumber
    first_name: str | None = None
    last_name: str | None = None


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
    fields = _verified_fields(init_data, bot_token, now, max_age_seconds)
    return _extract_user(fields.get("user"))


def parse_contact(
    contact_data: str,
    bot_token: str,
    now: datetime,
    max_age_seconds: int,
) -> TelegramContact:
    """Return the phone number Telegram signed for, or raise.

    `Telegram.WebApp.requestContact` hands the page a signed query string of the
    same shape as `initData`, carrying a `contact` object instead of a `user`.
    The number inside was verified by Telegram when the account was created, so
    a signature that checks out is stronger evidence than any code we could send
    and ask the person to type back.

    The signature is the whole of it: without this the endpoint would accept any
    phone number a caller cared to name, which is worse than not asking.
    """
    fields = _verified_fields(contact_data, bot_token, now, max_age_seconds)
    return _extract_contact(fields.get("contact"))


def _verified_fields(
    payload: str,
    bot_token: str,
    now: datetime,
    max_age_seconds: int,
) -> dict[str, str]:
    """Signature and freshness, shared by every signed payload Telegram sends."""
    if not bot_token:
        # Refusing loudly beats validating against an empty key, which would
        # accept a payload signed with an empty key by anyone who guessed that.
        raise ValidationFailedError(
            "Telegram orqali kirish sozlanmagan",
            details={"reason": "bot_token_missing"},
        )

    fields = dict(parse_qsl(payload, keep_blank_values=True))

    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise PermissionDeniedError("Telegram ma'lumotlari yaroqsiz")

    if not _signature_matches(fields, received_hash, bot_token):
        raise PermissionDeniedError("Telegram ma'lumotlari yaroqsiz")

    _require_fresh(fields.get("auth_date"), now, max_age_seconds)
    return fields


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


def _extract_contact(raw_contact: str | None) -> TelegramContact:
    """`contact` is a JSON object embedded in the query string as one value."""
    if not raw_contact:
        raise PermissionDeniedError("Telegram ma'lumotlari yaroqsiz")

    try:
        payload: Any = json.loads(raw_contact)
    except json.JSONDecodeError as error:
        raise PermissionDeniedError("Telegram ma'lumotlari yaroqsiz") from error

    if not isinstance(payload, dict):
        raise PermissionDeniedError("Telegram ma'lumotlari yaroqsiz")

    if not isinstance(payload.get("user_id"), int) or not payload.get("phone_number"):
        raise PermissionDeniedError("Telegram ma'lumotlari yaroqsiz")

    try:
        return TelegramContact.model_validate(payload)
    except ValidationError as error:
        # A signature that checks out but a number this product cannot serve —
        # a foreign one. That is the user's situation, not an attack, so it says
        # so plainly instead of "invalid Telegram data".
        raise ValidationFailedError(
            "Bu raqam bilan ro'yxatdan o'tib bo'lmaydi: O'zbekiston raqami kerak",
            details={"reason": "phone_not_supported"},
        ) from error
