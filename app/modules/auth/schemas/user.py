from datetime import datetime

from pydantic import BaseModel, Field

from app.core.schemas import PhoneNumber, ReadSchema, UpdateSchema
from app.modules.auth.enums import UserRole, UserStatus, UserTheme


class UserCreate(BaseModel):
    """Ichki foydalanish uchun. Ro'yxatdan o'tish `PhoneRegister` orqali ketadi.

    Bu yerda parol yo'q: parol o'rnatish alohida qadam (`POST /auth/password`),
    hodimlarga esa parol taklifnoma orqali beriladi.
    """

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: PhoneNumber | None = None
    email: str | None = None
    language_id: int
    district_id: int | None = None


class UserProfileUpdate(UpdateSchema):
    """Ism kiritilishi akkauntni `pending_profile` dan `active` ga o'tkazadi."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = None
    avatar_url: str | None = None
    language_id: int | None = None
    district_id: int | None = None
    theme: UserTheme | None = None


class UserRead(ReadSchema):
    """Profil ma'lumoti. `password_hash` va `login` qaytarilmaydi."""

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
    created_at: datetime


class UserListItem(ReadSchema):
    """Hodimlar yoki do'stlar ro'yxati uchun qisqa ko'rinish — aloqa ma'lumotisiz."""

    id: int
    first_name: str
    last_name: str
    avatar_url: str | None = None
