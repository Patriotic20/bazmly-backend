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
    """Taklifnomani o'qish. Na parol, na uning xeshi qaytariladi.

    Vaqtinchalik parol faqat taklifnoma yaratilgan paytdagi javobda ko'rinadi
    (`StaffInvitationCreated`) va boshqa hech qayerdan qayta o'qib bo'lmaydi —
    qayta o'qiladigan taklifnoma kassaga doimiy kalit bo'lib qolardi.
    """

    id: int
    venue_group_id: int
    venue_id: int | None = None
    full_name: str
    phone: str
    staff_role_id: int
    accepted_at: datetime | None = None
    expires_at: datetime


class StaffInvitationCreated(StaffInvitationRead):
    """Faqat yaratish javobida. Sirni tashiydigan yagona sxema.

    SMS yo'q, ya'ni hisob ma'lumotlarini hodimga yetkazadigan kanal ham yo'q:
    ularni bir marta shu javobda ko'rsatib, muassasa egasining o'ziga topshirish
    — taklifnomani umuman ishlatib bo'lmasligidan afzal. Sababi DECISIONS.md da.
    """

    login: str
    temporary_password: str
