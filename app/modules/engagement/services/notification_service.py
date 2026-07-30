from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import NotFoundError
from app.core.pagination import Page
from app.core.transports import get_push_sender
from app.modules.auth.repositories import DeviceRepository
from app.modules.engagement.models import Notification
from app.modules.engagement.repositories import NotificationRepository
from app.modules.engagement.schemas import NotificationRead, UnreadCountRead


class NotificationService:
    """In-app notifications, plus fire-and-forget push.

    `notify_in_transaction` is what booking and order services call so the
    notification row lands inside their unit of work — if the booking rolls back,
    so does the message about it.

    Push delivery is deliberately outside any transaction and never awaited for
    success: a dead token or a provider timeout must not roll back a booking the
    database already accepted.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.notifications = NotificationRepository(session)
        self.devices = DeviceRepository(session)

    async def notify_in_transaction(
        self,
        user_id: int,
        notification_type: str,
        title: str,
        body: str,
        payload: dict[str, Any] | None = None,
    ) -> Notification:
        return await self.notifications.create(
            Notification(
                user_id=user_id,
                type=notification_type,
                title=title,
                body=body,
                payload=payload,
                sent_at=utcnow_naive(),
            )
        )

    async def push_after_commit(self, user_id: int, title: str, body: str) -> None:
        """Called after the caller has committed. Failures are swallowed by design."""
        tokens = await self.devices.list_push_tokens_for_user(user_id)
        if tokens:
            await get_push_sender().send(list(tokens), title, body)

    async def list_for_user(
        self, user_id: int, limit: int = 20, offset: int = 0
    ) -> Page[NotificationRead]:
        page = await self.notifications.list_for_user(user_id, limit, offset)
        return Page(
            items=[NotificationRead.model_validate(row) for row in page.items],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        )

    async def unread_count(self, user_id: int) -> UnreadCountRead:
        return UnreadCountRead(unread=await self.notifications.count_unread(user_id))

    async def mark_read(self, notification_id: int) -> NotificationRead:
        updated = await self.notifications.mark_read(notification_id, utcnow_naive())
        if updated is None:
            raise NotFoundError("Bildirishnoma topilmadi yoki allaqachon o'qilgan")
        await self.session.commit()
        return NotificationRead.model_validate(updated)

    async def mark_all_read(self, user_id: int) -> Sequence[int]:
        ids = await self.notifications.mark_all_read(user_id, utcnow_naive())
        await self.session.commit()
        return ids
