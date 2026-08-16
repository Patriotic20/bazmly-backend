from pydantic import BaseModel, Field

from app.core.schemas import Password, PhoneNumber, ReadSchema


class PhoneCheck(BaseModel):
    """Kirishning birinchi qadami: raqam yuboriladi, boshqa hech narsa emas."""

    phone: PhoneNumber


class PhoneCheckResult(ReadSchema):
    """Mijoz keyin qaysi ekranni ko'rsatishini shu javob hal qiladi.

    Bu yerda ataylab token ham, foydalanuvchi haqidagi ma'lumot ham yo'q — bu
    autentifikatsiya emas, faqat yo'nalish.
    """

    phone: str
    registered: bool
    password_required: bool


class PhoneRegister(BaseModel):
    """Ikkinchi qadam, yangi raqam uchun: qolgan ma'lumot shu yerda kiritiladi.

    `password` ixtiyoriy. Berilsa, keyingi kirishlarda o'sha raqam uchun parol
    talab qilinadi; berilmasa, kirish uchun telefon raqamning o'zi yetarli.
    """

    phone: PhoneNumber
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: Password | None = None
    language_id: int | None = None
    district_id: int | None = None


class PhoneLogin(BaseModel):
    """Mavjud raqam bilan kirish.

    `password` bu yerda `Password` emas: hisobda saqlangan eski parol yangi
    uzunlik qoidasiga mos kelmasligi mumkin, va uzunlikni bu yerda rad etish
    "parol noto'g'ri" javobidan boshqa ma'no bermaydi.
    """

    phone: PhoneNumber
    password: str | None = Field(default=None, max_length=128)


class PasswordChange(BaseModel):
    """Parol hali o'rnatilmagan bo'lsa `current_password` talab qilinmaydi."""

    current_password: str | None = Field(default=None, max_length=128)
    new_password: Password


class StaffLogin(BaseModel):
    """Hodimlar telefon raqami bilan emas, berilgan login bilan kiradi."""

    login: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class TelegramLogin(BaseModel):
    """Mini App ochilganda Telegram bergan `initData` satri, o'zgartirilmagan holda.

    Bu satr imzolangan, shuning uchun uni qismlarga ajratib yuborish mumkin emas:
    imzo aynan shu ko'rinish uchun hisoblangan.
    """

    init_data: str = Field(min_length=1, max_length=4096)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(ReadSchema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user_id: int
    must_change_password: bool = False
    # `false` faqat ismi yo'q holda yaratilgan akkauntlarda bo'ladi — mijoz
    # shunda `/complete-profile` ekranini ko'rsatadi.
    profile_completed: bool = True
