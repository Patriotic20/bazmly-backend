from datetime import datetime

from app.core.schemas import ReadSchema
from app.modules.promotions.enums import UserPromoCodeSource, UserPromoCodeStatus


class UserPromoCodeRead(ReadSchema):
    """A Voucher tab card.

    `seconds_remaining` is `expires_at - now` computed by the service at read. The
    countdown is never stored, because a stored countdown is wrong one second later.
    """

    id: int
    code: str
    source: UserPromoCodeSource
    status: UserPromoCodeStatus
    expires_at: datetime
    used_at: datetime | None = None
    seconds_remaining: int = 0
