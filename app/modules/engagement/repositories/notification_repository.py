from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page
from app.modules.engagement.models import Notification


class NotificationRepository:
    """The Xabarlar screen groups client-side by Today / This Week / This Month
    from `sent_at`, so this only has to return them newest first."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, notification: Notification) -> Notification:
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def list_for_user(
        self, user_id: int, limit: int = 20, offset: int = 0
    ) -> Page[Notification]:
        total = int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.user_id == user_id)
                )
            ).scalar_one()
        )
        result = await self.session.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.sent_at.desc(), Notification.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return Page(items=list(result.scalars().all()), total=total, limit=limit, offset=offset)

    async def count_unread(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        return int(result.scalar_one())

    async def mark_read(self, notification_id: int, now: datetime) -> Notification | None:
        result = await self.session.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.read_at.is_(None))
            .values(read_at=now)
            .returning(Notification)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def mark_all_read(self, user_id: int, now: datetime) -> Sequence[int]:
        result = await self.session.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=now)
            .returning(Notification.id)
        )
        await self.session.flush()
        return list(result.scalars().all())
