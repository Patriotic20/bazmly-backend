from datetime import datetime

from pydantic import BaseModel, Field

from app.core.schemas import PhoneNumber, ReadSchema


class StaffInvitationCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    phone: PhoneNumber
    staff_role_id: int
    venue_id: int | None = None


class InvitationAccept(BaseModel):
    login: str = Field(min_length=1, max_length=32)
    temporary_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class StaffInvitationRead(ReadSchema):
    """`temp_password_hash` ham, ochiq parol ham qaytarilmaydi.

    Vaqtinchalik parol SMS orqali bir marta yuboriladi va API dan hech qachon
    qayta o'qib bo'lmaydi — qayta o'qiladigan taklifnoma kassaga doimiy kalit
    bo'lib qolardi.
    """

    id: int
    venue_group_id: int
    venue_id: int | None = None
    full_name: str
    phone: str
    staff_role_id: int
    sms_sent_at: datetime | None = None
    accepted_at: datetime | None = None
    expires_at: datetime
