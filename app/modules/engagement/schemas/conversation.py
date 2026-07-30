from datetime import datetime

from pydantic import BaseModel

from app.core.schemas import ReadSchema
from app.modules.engagement.schemas.message import MessageRead


class ConversationCreate(BaseModel):
    venue_id: int
    booking_id: int | None = None


class ConversationListItem(ReadSchema):
    """Suhbatlar ro'yxatidagi qator: suhbat, oxirgi xabar va o'qilmaganlar soni.

    Yuboruvchining o'z xabarlari o'qilmagan deb hisoblanmaydi.
    """

    id: int
    venue_id: int
    user_id: int
    booking_id: int | None = None
    last_message_at: datetime | None = None
    last_message: MessageRead | None = None
    unread_count: int = 0


class ConversationRead(ReadSchema):
    id: int
    venue_id: int
    user_id: int
    booking_id: int | None = None
    last_message_at: datetime | None = None
