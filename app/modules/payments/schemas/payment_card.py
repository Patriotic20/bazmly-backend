from datetime import datetime

from pydantic import BaseModel, Field

from app.core.schemas import ReadSchema
from app.modules.payments.enums import CardBrand


class PaymentCardCreate(BaseModel):
    """Karta raqami bu API ga hech qachon kelmaydi.

    Mijoz raqam va muddatni to'g'ridan-to'g'ri provayderga yuboradi va faqat
    qaytgan tokenni bu yerga joylaydi.
    """

    provider: str = Field(min_length=1, max_length=50)
    provider_token: str = Field(min_length=1, max_length=255)
    brand: CardBrand
    last_four: str = Field(min_length=4, max_length=4)
    holder_name: str = Field(min_length=1, max_length=200)
    expiry_month: int = Field(ge=1, le=12)
    expiry_year: int = Field(ge=2020, le=2100)
    is_default: bool = False


class PaymentCardRead(ReadSchema):
    """Saqlangan karta. `provider_token` qaytarilmaydi — u pul yechish kaliti."""

    id: int
    brand: CardBrand
    last_four: str
    holder_name: str
    expiry_month: int
    expiry_year: int
    is_default: bool
    verified_at: datetime | None = None
