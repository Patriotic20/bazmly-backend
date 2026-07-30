from app.modules.auth.schemas.auth import (
    OtpRequest,
    OtpRequested,
    OtpVerify,
    PhoneCheck,
    RefreshRequest,
    SocialLogin,
    StaffLogin,
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
    "OtpRequest",
    "OtpRequested",
    "OtpVerify",
    "PhoneCheck",
    "RefreshRequest",
    "SocialLogin",
    "StaffLogin",
    "TokenPair",
    "UserCreate",
    "UserListItem",
    "UserProfileUpdate",
    "UserRead",
]
