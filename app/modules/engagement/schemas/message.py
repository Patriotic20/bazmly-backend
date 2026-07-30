from datetime import datetime

from pydantic import BaseModel, Field

from app.core.schemas import ReadSchema
from app.modules.engagement.enums import MessageSenderType


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class MessageRead(ReadSchema):
    id: int
    conversation_id: int
    sender_type: MessageSenderType
    sender_user_id: int
    body: str
    read_at: datetime | None = None
    created_at: datetime
