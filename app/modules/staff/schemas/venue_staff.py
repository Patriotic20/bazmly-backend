from datetime import datetime

from pydantic import BaseModel, Field

from app.core.schemas import ReadSchema, UpdateSchema
from app.modules.auth.schemas import UserListItem


class VenueStaffCreate(BaseModel):
    venue_id: int | None = None
    user_id: int
    staff_role_id: int


class VenueStaffUpdate(UpdateSchema):
    """Hodim kartasidan tahrirlash.

    Ism faqat hodim uchun ochilgan akkauntda o'zgaradi — o'z akkaunti bilan
    ishlaydigan odamning ismini egasi o'zgartira olmaydi.
    """

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    staff_role_id: int | None = None
    is_active: bool | None = None


class StaffPasswordReset(BaseModel):
    """Yangi parol faqat shu javobda ko'rinadi, keyin hech qayerdan o'qib bo'lmaydi."""

    login: str
    temporary_password: str


class VenueStaffListItem(ReadSchema):
    """Hodimlar kartasi. Parol va login qaytarilmaydi — ular `users` da saqlanadi."""

    id: int
    venue_id: int | None = None
    staff_role_id: int
    role_name: str
    is_active: bool
    user: UserListItem


class VenueStaffRead(ReadSchema):
    id: int
    venue_group_id: int
    venue_id: int | None = None
    user_id: int
    staff_role_id: int
    role_scope: str
    is_active: bool
    invited_at: datetime
    activated_at: datetime | None = None
    deactivated_at: datetime | None = None


class StaffCountsRead(ReadSchema):
    """Jami / Aktiv / Noaktiv."""

    total: int
    active: int
    inactive: int
