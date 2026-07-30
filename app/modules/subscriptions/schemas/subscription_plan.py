from decimal import Decimal

from app.core.schemas import Money, ReadSchema
from app.modules.subscriptions.enums import SubscriptionPlanCode


class SubscriptionPlanRead(ReadSchema):
    id: int
    code: SubscriptionPlanCode
    name: str
    description: str | None = None
    price: Money
    currency: str
    duration_days: int
    benefit_percent: Decimal
    sort_order: int
