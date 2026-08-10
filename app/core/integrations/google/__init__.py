"""Google Sign-In. Verification only — we never speak OAuth ourselves."""

from app.core.integrations.google.verifier import (
    GoogleAuthError,
    GoogleIdentity,
    GoogleIdTokenVerifier,
    GoogleNotConfiguredError,
    close_google_verifier,
    get_google_verifier,
    set_google_verifier,
)

__all__ = [
    "GoogleAuthError",
    "GoogleIdTokenVerifier",
    "GoogleIdentity",
    "GoogleNotConfiguredError",
    "close_google_verifier",
    "get_google_verifier",
    "set_google_verifier",
]
