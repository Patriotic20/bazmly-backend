from datetime import datetime
from typing import Any

from app.core.schemas import ReadSchema


class NotificationRead(ReadSchema):
    """Xabarlar ekrani `sent_at` bo'yicha Bugun / Shu hafta / Shu oy ga ajratadi."""

    id: int
    type: str
    title: str
    body: str
    payload: dict[str, Any] | None = None
    read_at: datetime | None = None
    sent_at: datetime


class UnreadCountRead(ReadSchema):
    unread: int
