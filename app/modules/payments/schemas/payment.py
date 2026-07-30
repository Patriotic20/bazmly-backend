from datetime import datetime
from typing import Self

from pydantic import BaseModel, model_validator

from app.core.schemas import Money, ReadSchema
from app.modules.payments.enums import PaymentKind, PaymentStatus


class PaymentCreate(BaseModel):
    kind: PaymentKind
    amount: Money
    currency: str = "UZS"
    booking_id: int | None = None
    subscription_id: int | None = None
    card_id: int | None = None
    provider: str = "manual"

    @model_validator(mode="after")
    def _exactly_one_target(self) -> Self:
        """Mirrors the CHECK constraint so the 422 beats the 500."""
        targets = [self.booking_id, self.subscription_id]
        if sum(t is not None for t in targets) != 1:
            raise ValueError(
                "`booking_id` yoki `subscription_id` dan faqat bittasi to'ldirilishi kerak"
            )
        return self


class PaymentRead(ReadSchema):
    id: int
    booking_id: int | None = None
    subscription_id: int | None = None
    kind: PaymentKind
    amount: Money
    currency: str
    status: PaymentStatus
    paid_at: datetime | None = None


class BookingPaymentSummary(ReadSchema):
    booking_id: int
    total_amount: Money
    paid_amount: Money
    outstanding: Money
    currency: str
