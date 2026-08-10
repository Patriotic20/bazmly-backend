"""What the Google verifier accepts, and — mostly — what it refuses.

Every case here was reachable through the old `POST /auth/social/{provider}`,
which took `provider_user_id` and `provider_email` straight out of the request
body and believed them. These tests exist so that cannot come back.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.integrations.google import (
    GoogleAuthError,
    GoogleIdTokenVerifier,
    GoogleNotConfiguredError,
)

CLIENT_ID = "test-client.apps.googleusercontent.com"
JWKS_URL = "https://example.invalid/certs"
KID = "test-key-1"


def private_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_PEM = private_pem(_KEY)


def jwks_body(kid: str = KID) -> dict[str, Any]:
    """Google's key set, in the shape it actually publishes."""
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key(), as_dict=True)
    return {"keys": [{**jwk, "kid": kid, "use": "sig", "alg": "RS256"}]}


def id_token(**overrides: Any) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "google-user-1",
        "email": "ali@example.com",
        "email_verified": True,
        "given_name": "Ali",
        "family_name": "Valiyev",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    claims.update(overrides)
    return jwt.encode(claims, _PRIVATE_PEM, algorithm="RS256", headers={"kid": KID})


def build(
    *, client_ids: list[str] | None = None, body: dict[str, Any] | None = None
) -> GoogleIdTokenVerifier:
    """A verifier whose JWKS fetch is answered in-process, never over a network."""
    payload = jwks_body() if body is None else body

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return GoogleIdTokenVerifier(
        jwks_url=JWKS_URL,
        client_ids=[CLIENT_ID] if client_ids is None else client_ids,
        timeout_seconds=1.0,
        cache_seconds=60,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_a_valid_token_yields_the_claims_we_act_on() -> None:
    identity = await build().verify(id_token())

    assert identity.subject == "google-user-1"
    assert identity.email == "ali@example.com"
    assert identity.email_verified is True
    assert identity.first_name == "Ali"
    assert identity.last_name == "Valiyev"


async def test_a_token_for_another_client_is_refused() -> None:
    """The signature is Google's and every claim is well-formed. It is still not
    ours — an `aud` check is what stops another app's token signing in here."""
    with pytest.raises(GoogleAuthError):
        await build().verify(id_token(aud="someone-else.apps.googleusercontent.com"))


async def test_a_token_from_another_issuer_is_refused() -> None:
    with pytest.raises(GoogleAuthError):
        await build().verify(id_token(iss="https://evil.example.com"))


async def test_an_expired_token_is_refused() -> None:
    past = datetime.now(UTC) - timedelta(hours=2)
    with pytest.raises(GoogleAuthError):
        await build().verify(id_token(iat=past, exp=past + timedelta(minutes=1)))


async def test_a_token_signed_by_someone_else_is_refused() -> None:
    """The whole point: a self-signed token with perfect claims must not verify."""
    pem = private_pem(rsa.generate_private_key(public_exponent=65537, key_size=2048))
    now = datetime.now(UTC)
    forged = jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "aud": CLIENT_ID,
            "sub": "victim",
            "email": "victim@example.com",
            "email_verified": True,
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        pem,
        algorithm="RS256",
        headers={"kid": KID},
    )

    with pytest.raises(GoogleAuthError):
        await build().verify(forged)


async def test_an_unsigned_token_is_refused() -> None:
    """`alg: none` is the classic bypass; only RS256 is on the allow-list."""
    now = datetime.now(UTC)
    unsigned = jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "aud": CLIENT_ID,
            "sub": "victim",
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        key="",
        algorithm="none",
        headers={"kid": KID},
    )

    with pytest.raises(GoogleAuthError):
        await build().verify(unsigned)


async def test_an_unknown_key_id_is_refused_after_one_refetch() -> None:
    with pytest.raises(GoogleAuthError):
        await build(body=jwks_body(kid="some-other-key")).verify(id_token())


async def test_no_configured_client_id_refuses_before_touching_the_token() -> None:
    """An empty `client_ids` means no `aud` could ever match, so accepting
    anything would mean accepting everything."""
    with pytest.raises(GoogleNotConfiguredError):
        await build(client_ids=[]).verify(id_token())


async def test_the_key_set_is_fetched_once_and_reused() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=jwks_body())

    verifier = GoogleIdTokenVerifier(
        jwks_url=JWKS_URL,
        client_ids=[CLIENT_ID],
        timeout_seconds=1.0,
        cache_seconds=60,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    await verifier.verify(id_token())
    await verifier.verify(id_token())

    assert calls == 1, "the second sign-in must not put a network hop on the path"
