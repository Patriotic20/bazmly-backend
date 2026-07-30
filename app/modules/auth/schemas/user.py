from datetime import datetime

from pydantic import BaseModel, Field

from app.core.schemas import PhoneNumber, ReadSchema, UpdateSchema
from app.modules.auth.enums import UserRole, UserStatus, UserTheme


class UserCreate(BaseModel):
    """Faqat tasdiqlash kodi ishlatilgandan keyin yaratiladi.

    Bu yerda parol yo'q: mijozlar SMS kod bilan kiradi, hodimlarga esa parol
    taklifnoma orqali beriladi — ro'yxatdan o'tishda tanlanmaydi.
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
    phone_verified_at: datetime | None = None
    created_at: datetime


class UserListItem(ReadSchema):
    """Hodimlar yoki do'stlar ro'yxati uchun qisqa ko'rinish — aloqa ma'lumotisiz."""

    id: int
    first_name: str
    last_name: str
    avatar_url: str | None = None
