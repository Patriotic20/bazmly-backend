"""Enum values for the `auth` module.

Re-exported from the model files that declare them, so models and schemas
share one object per enum. Schemas import from here; nothing redeclares an
enum. See DECISIONS.md for why the declarations still sit in the models.
"""

from app.modules.auth.models.device import DevicePlatform
from app.modules.auth.models.friendship import FriendshipStatus
from app.modules.auth.models.user import UserRole, UserStatus, UserTheme

__all__ = [
    "DevicePlatform",
    "FriendshipStatus",
    "UserRole",
    "UserStatus",
    "UserTheme",
]
