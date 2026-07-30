from datetime import datetime

from pydantic import BaseModel, Field

from app.core.schemas import PhoneNumber, ReadSchema, UpdateSchema
from app.modules.auth.enums import UserRole, UserStatus, UserTheme


class UserCreate(BaseModel):
    """Only reached after a verification code has been consumed.

    There is no password here: customers authenticate by OTP, and staff
    credentials are issued by an invitation, never chosen at signup.
    """

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: PhoneNumber | None = None
    email: str | None = None
    language_id: int
    district_id: int | None = None


class UserProfileUpdate(UpdateSchema):
    """Setting a name is what promotes `pending_profile` to `active`."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = None
    avatar_url: str | None = None
    language_id: int | None = None
    district_id: int | None = None
    theme: UserTheme | None = None


class UserRead(ReadSchema):
    """No `password_hash`, and no `login` — a staff login is a credential."""

    id: int
    first_name: str
    last_name: str
    phone: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    language_id: int
    district_id: int | None = None
    role: UserRole
    status: UserStatus
    theme: UserTheme
    phone_verified_at: datetime | None = None
    created_at: datetime


class UserListItem(ReadSchema):
    """The shape a staff list or a friend list needs — no contact details."""

    id: int
    first_name: str
    last_name: str
    avatar_url: str | None = None
