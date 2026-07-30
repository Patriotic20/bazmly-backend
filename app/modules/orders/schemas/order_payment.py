from datetime import datetime

from pydantic import BaseModel

from app.core.schemas import Money, ReadSchema
from app.modules.orders.enums import OrderPaymentMethod


class OrderPaymentCreate(BaseModel):
    method: OrderPaymentMethod
    amount: Money
    provider_transaction_id: str | None = None
    change_amount: Money | None = None


class OrderPaymentRead(ReadSchema):
    """Split payments are one order, several rows."""

    id: int
    method: OrderPaymentMethod
    amount: Money
    currency: str
    paid_at: datetime
    change_amount: Money | None = None
