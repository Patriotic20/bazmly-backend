from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.modules.engagement.enums import MessageSenderType
from app.modules.engagement.repositories import ConversationRepository, ConversationRow
from app.modules.engagement.schemas import (
    ConversationListItem,
    ConversationRead,
    MessageCreate,
    MessageRead,
)


class ConversationService:
    """Backs "Xabar yuborish" on the active-booking card.

    One thread per user and venue: a new booking attaches to the existing thread
    rather than forking the history, so a guest's conversation with a venue reads
    as one conversation.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conversations = ConversationRepository(session)

    async def open(
        self, user_id: int, venue_id: int, booking_id: int | None = None
    ) -> ConversationRead:
        conversation = await self.conversations.get_or_create(user_id, venue_id, booking_id)
        await self.session.commit()
        return ConversationRead.model_validate(conversation)

    async def list_for_user(self, user_id: int) -> Sequence[ConversationListItem]:
        rows = await self.conversations.list_for_user(user_id)
        return [self._to_list_item(row) for row in rows]

    async def list_for_venue(self, venue_id: int) -> Sequence[ConversationListItem]:
        rows = await self.conversations.list_for_venue(venue_id)
        return [self._to_list_item(row) for row in rows]

    async def send(
        self,
        conversation_id: int,
        sender_user_id: int,
        sender_type: str,
        payload: MessageCreate,
    ) -> MessageRead:
        """Appends and moves `last_message_at` in one flush, so the inbox ordering
        can never lag behind its own messages."""
        conversation = await self.conversations.get_by_id(conversation_id)
        if conversation is None:
            raise NotFoundError("Suhbat topilmadi")
        if sender_type == MessageSenderType.USER and conversation.user_id != sender_user_id:
            raise PermissionDeniedError("Bu suhbat boshqa foydalanuvchiga tegishli")

        message = await self.conversations.add_message(
            conversation_id=conversation_id,
            sender_type=sender_type,
            sender_user_id=sender_user_id,
            body=payload.body,
            now=utcnow_naive(),
        )
        await self.session.commit()
        return MessageRead.model_validate(message)

    async def history(
        self, conversation_id: int, limit: int = 50, offset: int = 0
    ) -> Sequence[MessageRead]:
        rows = await self.conversations.list_messages(conversation_id, limit, offset)
        return [MessageRead.model_validate(row) for row in rows]

    async def mark_read(self, conversation_id: int, reader_type: str) -> Sequence[int]:
        """Marks the other side's messages only — a sender never marks their own."""
        ids = await self.conversations.mark_read(conversation_id, reader_type, utcnow_naive())
        await self.session.commit()
        return ids

    def _to_list_item(self, row: ConversationRow) -> ConversationListItem:
        return ConversationListItem(
            id=row.conversation.id,
            venue_id=row.conversation.venue_id,
            user_id=row.conversation.user_id,
            booking_id=row.conversation.booking_id,
            last_message_at=row.conversation.last_message_at,
            last_message=(
                MessageRead.model_validate(row.last_message)
                if row.last_message is not None
                else None
            ),
            unread_count=row.unread_count,
        )
