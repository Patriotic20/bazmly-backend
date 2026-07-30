from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.core.schemas import Money, PromoCodeStr, ReadSchema
from app.modules.promotions.enums import DiscountType, PromoAppliesTo


class PromoCodeApply(BaseModel):
    code: PromoCodeStr


class PromoCodeRead(ReadSchema):
    id: int
    code: str
    discount_type: DiscountType
    value: Decimal
    applies_to: PromoAppliesTo
    min_amount: Money | None = None
    max_discount: Money | None = None
    valid_from: datetime
    valid_to: datetime


class PromoCodePreview(ReadSchema):
    """What the discount would be, before anything is written."""

    code: str
    discount_type: DiscountType
    discount_amount: Money
    subtotal: Money
    total_after_discount: Money
    currency: str
