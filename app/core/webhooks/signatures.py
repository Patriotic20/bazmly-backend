"""Provider signature verification.

Constant-time comparison, and a missing configured secret means the provider is
**off** rather than open: an empty secret compared against an empty header would
otherwise authenticate everyone.
"""

import hashlib
import hmac


def verify_signature(payload: bytes, signature: str | None, secret: str) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())
