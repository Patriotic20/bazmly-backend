from app.modules.auth.schemas.auth import (
    PasswordChange,
    PhoneCheck,
    PhoneCheckResult,
    PhoneLogin,
    PhoneRegister,
    RefreshRequest,
    StaffLogin,
    TelegramContactShare,
    TelegramLogin,
    TokenPair,
)
from app.modules.auth.schemas.device import DeviceCreate, DeviceRead
from app.modules.auth.schemas.friendship import (
    FriendRead,
    FriendshipCreate,
    FriendshipRead,
    FriendshipRespond,
)
from app.modules.auth.schemas.user import (
    UserCreate,
    UserListItem,
    UserProfileUpdate,
    UserRead,
)

__all__ = [
    "DeviceCreate",
    "DeviceRead",
    "FriendRead",
    "FriendshipCreate",
    "FriendshipRead",
    "FriendshipRespond",
    "PasswordChange",
    "PhoneCheck",
    "PhoneCheckResult",
    "PhoneLogin",
    "PhoneRegister",
    "RefreshRequest",
    "StaffLogin",
    "TelegramContactShare",
    "TelegramLogin",
    "TokenPair",
    "UserCreate",
    "UserListItem",
    "UserProfileUpdate",
    "UserRead",
]
