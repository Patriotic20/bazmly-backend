from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.engagement.models import Conversation, Message, MessageSenderType


@dataclass(frozen=True, slots=True)
class ConversationRow:
    conversation: Conversation
    last_message: Message | None
    unread_count: int


class ConversationRepository:
    """Backs "Xabar yuborish" on the active-booking card. Messages are written and
    read through their conversation, never on their own."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, conversation_id: int) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self, user_id: int, venue_id: int, booking_id: int | None = None
    ) -> Conversation:
        """One thread per user and venue. A booking id attaches the thread to a
        visit without splitting the history into a new thread each time."""
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.user_id == user_id, Conversation.venue_id == venue_id
            )
        )
        conversation = result.scalar_one_or_none()
        if conversation is not None:
            if booking_id is not None and conversation.booking_id is None:
                conversation.booking_id = booking_id
                await self.session.flush()
            return conversation

        conversation = Conversation(user_id=user_id, venue_id=venue_id, booking_id=booking_id)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    def _rows_statement(self, reader_type: str) -> tuple[ColumnElement[int], ColumnElement[int]]:
        """Last message id and unread count, as correlated subqueries."""
        last_message_id = (
            select(Message.id)
            .where(Message.conversation_id == Conversation.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
            .correlate(Conversation)
            .scalar_subquery()
        )
        unread_count = (
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == Conversation.id,
                Message.read_at.is_(None),
                Message.sender_type != reader_type,
            )
            .correlate(Conversation)
            .scalar_subquery()
        )
        return last_message_id, unread_count

    async def list_for_user(self, user_id: int) -> Sequence[ConversationRow]:
        last_message_id, unread_count = self._rows_statement(MessageSenderType.USER)
        result = await self.session.execute(
            select(Conversation, Message, unread_count)
            .outerjoin(Message, Message.id == last_message_id)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.id)
        )
        return [
            ConversationRow(conversation=row[0], last_message=row[1], unread_count=int(row[2]))
            for row in result.all()
        ]

    async def list_for_venue(self, venue_id: int) -> Sequence[ConversationRow]:
        last_message_id, unread_count = self._rows_statement(MessageSenderType.VENUE)
        result = await self.session.execute(
            select(Conversation, Message, unread_count)
            .outerjoin(Message, Message.id == last_message_id)
            .where(Conversation.venue_id == venue_id)
            .order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.id)
        )
        return [
            ConversationRow(conversation=row[0], last_message=row[1], unread_count=int(row[2]))
            for row in result.all()
        ]

    async def add_message(
        self,
        conversation_id: int,
        sender_type: str,
        sender_user_id: int,
        body: str,
        now: datetime,
    ) -> Message:
        """Appends and moves the thread's `last_message_at` in the same flush, so
        the inbox ordering can never lag behind its own messages."""
        message = Message(
            conversation_id=conversation_id,
            sender_type=sender_type,
            sender_user_id=sender_user_id,
            body=body,
        )
        self.session.add(message)
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(last_message_at=now)
        )
        await self.session.flush()
        return message

    async def list_messages(
        self, conversation_id: int, limit: int = 50, offset: int = 0
    ) -> Sequence[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def mark_read(
        self, conversation_id: int, reader_type: str, now: datetime
    ) -> Sequence[int]:
        """Marks the *other* side's messages read — a sender never marks their own.
        Returns the affected ids."""
        result = await self.session.execute(
            update(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.sender_type != reader_type,
                Message.read_at.is_(None),
            )
            .values(read_at=now)
            .returning(Message.id)
        )
        await self.session.flush()
        return list(result.scalars().all())
