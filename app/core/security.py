"""Hashing and secret generation.

One-way only. Account passwords, refresh tokens and temporary staff passwords are
stored as hashes and compared with a constant-time equality check, so a database
leak does not hand over live credentials and a timing difference does not leak a
prefix.
"""

import hashlib
import hmac
import secrets
import string
from datetime import UTC, datetime, timedelta

import jwt

PBKDF2_ROUNDS = 240_000
SALT_BYTES = 16

LOGIN_LENGTH = 8
PASSWORD_LENGTH = 10

# Ambiguous glyphs removed: these are read off a screen and typed by hand.
_LOGIN_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_PASSWORD_ALPHABET = string.ascii_letters.replace("l", "").replace("O", "") + "23456789"


def hash_secret(secret: str) -> str:
    """PBKDF2-SHA256 with a per-secret salt, stored as `salt$digest`."""
    salt = secrets.token_hex(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(), PBKDF2_ROUNDS).hex()
    return f"{salt}${digest}"


def verify_secret(secret: str, stored: str) -> bool:
    """Constant-time comparison. A malformed stored value is a failure, not a crash."""
    salt, _, expected = stored.partition("$")
    if not salt or not expected:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(), PBKDF2_ROUNDS).hex()
    return hmac.compare_digest(digest, expected)


def generate_login(prefix: str = "bz") -> str:
    body = "".join(secrets.choice(_LOGIN_ALPHABET) for _ in range(LOGIN_LENGTH))
    return f"{prefix}{body}"


def generate_password(length: int = PASSWORD_LENGTH) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def generate_token(nbytes: int = 24) -> str:
    return secrets.token_urlsafe(nbytes)


# --- JWT ---------------------------------------------------------------------

ACCESS_TOKEN_TTL_MINUTES = 15
JWT_ALGORITHM = "HS256"
TOKEN_TYPE_ACCESS = "access"


class TokenError(Exception):
    """A token could not be decoded, or is not the type the caller expected."""


def encode_access_token(
    user_id: int,
    secret: str,
    now: datetime,
    ttl_minutes: int = ACCESS_TOKEN_TTL_MINUTES,
) -> str:
    """A short-lived stateless bearer credential.

    It deliberately carries no role or permission claim. Authority is read from
    `venue_staff` on every request, so demoting someone takes effect immediately
    rather than whenever their token happens to expire.

    `jti` is present so an access token can be denylisted later without changing
    the claim set.
    """
    issued_at = now.replace(tzinfo=UTC)
    payload = {
        "sub": str(user_id),
        "jti": secrets.token_urlsafe(8),
        "type": TOKEN_TYPE_ACCESS,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret: str) -> int:
    """Return the user id, or raise `TokenError`.

    The `type` claim is checked explicitly: a refresh token is also a signed
    string, and without this check one would be accepted as an access token.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as error:
        raise TokenError(str(error)) from error

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise TokenError("Not an access token")

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise TokenError("Malformed subject claim")
    return int(subject)
