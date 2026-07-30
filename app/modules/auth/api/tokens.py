"""Access-token minting at the API boundary.

`AuthService` owns the refresh-token lifecycle — the row, its hash, rotation and
revocation. An access token has no row: it is a stateless bearer credential, and
producing it is a transport concern, so it is minted here and the opaque one the
service returns is discarded. See DECISIONS.md.
"""

from app.core.config import settings
from app.core.database.mixins import utcnow_naive
from app.core.security import encode_access_token
from app.modules.auth.schemas import TokenPair


def with_access_token(pair: TokenPair) -> TokenPair:
    """Replace the service's placeholder access token with a signed JWT."""
    token = encode_access_token(
        pair.user_id,
        settings.security.secret_key,
        utcnow_naive(),
        settings.security.access_token_ttl_minutes,
    )
    return pair.model_copy(
        update={
            "access_token": token,
            "expires_in_seconds": settings.security.access_token_ttl_minutes * 60,
        }
    )
