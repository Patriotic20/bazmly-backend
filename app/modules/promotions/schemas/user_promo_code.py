from datetime import datetime

from app.core.schemas import ReadSchema
from app.modules.promotions.enums import UserPromoCodeSource, UserPromoCodeStatus


class UserPromoCodeRead(ReadSchema):
    """Promokodlar bo'limidagi karta.

    `seconds_remaining` o'qish paytida hisoblanadi. Saqlangan sanoq bir
    sekunddan keyin noto'g'ri bo'lib qoladi.
    """

    id: int
    code: str
    source: UserPromoCodeSource
    status: UserPromoCodeStatus
    expires_at: datetime
    used_at: datetime | None = None
    seconds_remaining: int = 0
