from pydantic import BaseModel, Field

from app.core.schemas import PhoneNumber, ReadSchema
from app.modules.auth.enums import AuthProvider, VerificationChannel, VerificationPurpose


class OtpRequest(BaseModel):
    destination: str
    channel: VerificationChannel = VerificationChannel.SMS
    purpose: VerificationPurpose = VerificationPurpose.REGISTRATION


class OtpVerify(BaseModel):
    destination: str
    code: str = Field(min_length=4, max_length=8)
    purpose: VerificationPurpose = VerificationPurpose.REGISTRATION


class StaffLogin(BaseModel):
    """Hodimlar telefon raqami bilan emas, berilgan login bilan kiradi."""

    login: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class SocialLogin(BaseModel):
    provider: AuthProvider
    provider_user_id: str
    provider_email: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class OtpRequested(ReadSchema):
    """Kodning o'zi qaytarilmaydi. Faqat amal qilish muddati."""

    destination: str
    expires_in_seconds: int


class TokenPair(ReadSchema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user_id: int
    must_change_password: bool = False


class PhoneCheck(BaseModel):
    phone: PhoneNumber
