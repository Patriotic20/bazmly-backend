from datetime import datetime

from pydantic import BaseModel

from app.core.schemas import ReadSchema
from app.modules.subscriptions.enums import UserSubscriptionStatus


class UserSubscriptionCreate(BaseModel):
    plan_id: int
    auto_renew: bool = True


class UserSubscriptionRead(ReadSchema):
    id: int
    plan_id: int
    status: UserSubscriptionStatus
    started_at: datetime
    current_period_start: datetime
    current_period_end: datetime
    next_payment_at: datetime | None = None
    auto_renew: bool
    cancelled_at: datetime | None = None
