from datetime import datetime

from pydantic import BaseModel, Field

from app.core.schemas import ReadSchema
from app.modules.payments.enums import CardBrand


class PaymentCardCreate(BaseModel):
    """The PAN never reaches this API.

    The client sends the number and expiry straight to the provider and posts back
    only the returned token, so nothing here can leak a card number.
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
    """No `provider_token` — it is a bearer credential for charging the card."""

    id: int
    brand: CardBrand
    last_four: str
    holder_name: str
    expiry_month: int
    expiry_year: int
    is_default: bool
    verified_at: datetime | None = None
