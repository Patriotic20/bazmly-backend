"""Google Sign-In `id_token` verification.

The client runs the OAuth dance with Google and sends us the resulting
`id_token`. Nothing else it sends is trusted: the stable user id, the email and
the name are all read out of a token whose RS256 signature was checked against
Google's published keys, whose `aud` is one of our own client ids and whose `iss`
is Google. That is the whole point — the previous social endpoint took the email
straight from the request body, which let anyone sign in as anyone.

The JWKS is cached in-process. Google rotates these keys roughly daily and
publishes a `Cache-Control: max-age`; a cache miss on an unknown `kid` forces one
refresh, so a rotation costs a single extra fetch rather than a failed sign-in.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx
import jwt

from app.core.config import settings

logger = logging.getLogger("app.google")

# Google mints both spellings and has done for years. Both are legitimate.
ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})

ALGORITHMS = ["RS256"]

# Even when Google asks for a shorter cache, refetching on every sign-in would
# put a network round trip on the login path for no security gain.
MIN_CACHE_SECONDS = 600


class GoogleAuthError(Exception):
    """The token is not a valid Google identity token for this application."""


class GoogleNotConfiguredError(GoogleAuthError):
    """No client id is configured, so no `aud` could ever be accepted."""


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    """The verified claims we act on.

    `subject` is Google's stable per-account id and is what `auth_identities`
    keys on — the email can change, `sub` cannot.
    """

    subject: str
    email: str | None
    email_verified: bool
    first_name: str
    last_name: str


class GoogleIdTokenVerifier:
    """Fetches and caches Google's JWKS, then verifies tokens against it."""

    def __init__(
        self,
        *,
        jwks_url: str,
        client_ids: list[str],
        timeout_seconds: float,
        cache_seconds: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.jwks_url = jwks_url
        self.client_ids = client_ids
        self.timeout_seconds = timeout_seconds
        self.cache_seconds = max(cache_seconds, MIN_CACHE_SECONDS)
        self._client = client
        self._owns_client = client is None
        self._jwks: jwt.PyJWKSet | None = None
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def verify(self, id_token: str) -> GoogleIdentity:
        if not self.client_ids:
            raise GoogleNotConfiguredError(
                "Google sign-in is not configured: GOOGLE__CLIENT_IDS is empty"
            )

        key = await self._signing_key(id_token)
        try:
            claims = jwt.decode(
                id_token,
                key,
                algorithms=ALGORITHMS,
                audience=self.client_ids,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            )
        except jwt.PyJWTError as error:
            raise GoogleAuthError(str(error)) from error

        # Checked here rather than via `jwt.decode(issuer=...)` because two
        # spellings are valid and that parameter takes only one.
        if claims.get("iss") not in ISSUERS:
            raise GoogleAuthError(f"Unexpected issuer {claims.get('iss')!r}")

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise GoogleAuthError("Missing subject claim")

        return GoogleIdentity(
            subject=subject,
            email=claims.get("email") or None,
            email_verified=bool(claims.get("email_verified")),
            first_name=str(claims.get("given_name") or ""),
            last_name=str(claims.get("family_name") or ""),
        )

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
        self._client = None

    # --- internals -----------------------------------------------------------

    async def _signing_key(self, id_token: str) -> jwt.PyJWK:
        """Resolve the token's `kid`, refetching once if it is unknown.

        An unknown `kid` on a fresh cache means Google rotated; refusing without
        retrying would fail every sign-in until the TTL expired.
        """
        try:
            kid = jwt.get_unverified_header(id_token).get("kid")
        except jwt.PyJWTError as error:
            raise GoogleAuthError(str(error)) from error
        if not isinstance(kid, str) or not kid:
            raise GoogleAuthError("Token header carries no key id")

        jwks = await self._load_jwks(force=False)
        key = _find(jwks, kid)
        if key is None:
            jwks = await self._load_jwks(force=True)
            key = _find(jwks, kid)
        if key is None:
            raise GoogleAuthError(f"Unknown signing key {kid!r}")
        return key

    async def _load_jwks(self, *, force: bool) -> jwt.PyJWKSet:
        async with self._lock:
            cached = self._jwks
            age = time.monotonic() - self._fetched_at
            if cached is not None and age < self.cache_seconds and not force:
                return cached

            if self._client is None:
                self._client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds))
                self._owns_client = True

            try:
                response = await self._client.get(self.jwks_url, timeout=self.timeout_seconds)
                response.raise_for_status()
                jwks = jwt.PyJWKSet.from_dict(response.json())
            except (httpx.HTTPError, ValueError, jwt.PyJWTError) as error:
                # A stale set still verifies tokens signed by keys we already hold,
                # which beats locking everyone out while Google is unreachable.
                if self._jwks is not None:
                    logger.warning("Google JWKS refresh failed, using cached keys: %s", error)
                    return self._jwks
                raise GoogleAuthError(f"Could not fetch Google signing keys: {error}") from error

            self._jwks = jwks
            self._fetched_at = time.monotonic()
            return jwks


def _find(jwks: jwt.PyJWKSet, kid: str) -> jwt.PyJWK | None:
    for key in jwks.keys:
        if key.key_id == kid:
            return key
    return None


_verifier: GoogleIdTokenVerifier | None = None


def get_google_verifier() -> GoogleIdTokenVerifier:
    """The process-wide verifier, built lazily from settings."""
    global _verifier
    if _verifier is None:
        _verifier = GoogleIdTokenVerifier(
            jwks_url=settings.google.jwks_url,
            client_ids=settings.google.client_ids,
            timeout_seconds=settings.google.timeout_seconds,
            cache_seconds=settings.google.jwks_cache_seconds,
        )
    return _verifier


def set_google_verifier(verifier: GoogleIdTokenVerifier | None) -> None:
    """Test seam."""
    global _verifier
    _verifier = verifier


async def close_google_verifier() -> None:
    global _verifier
    if _verifier is not None:
        await _verifier.aclose()
        _verifier = None
