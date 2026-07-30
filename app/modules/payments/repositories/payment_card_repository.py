from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import PaymentCard


class PaymentCardRepository:
    """Only ever holds the provider's token — never the PAN."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, card_id: int) -> PaymentCard | None:
        result = await self.session.execute(select(PaymentCard).where(PaymentCard.id == card_id))
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: int) -> Sequence[PaymentCard]:
        result = await self.session.execute(
            select(PaymentCard)
            .where(PaymentCard.user_id == user_id)
            .order_by(PaymentCard.is_default.desc(), PaymentCard.id)
        )
        return result.scalars().all()

    async def get_default(self, user_id: int) -> PaymentCard | None:
        result = await self.session.execute(
            select(PaymentCard).where(
                PaymentCard.user_id == user_id, PaymentCard.is_default.is_(True)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_token(self, provider_token: str) -> PaymentCard | None:
        result = await self.session.execute(
            select(PaymentCard).where(PaymentCard.provider_token == provider_token)
        )
        return result.scalar_one_or_none()

    async def set_default(self, user_id: int, card_id: int) -> PaymentCard | None:
        """Clears the previous default in the same flush.

        Both statements land in the caller's transaction, so no reader can observe
        the moment where the user has two defaults or none.
        """
        await self.session.execute(
            update(PaymentCard)
            .where(
                PaymentCard.user_id == user_id,
                PaymentCard.id != card_id,
                PaymentCard.is_default.is_(True),
            )
            .values(is_default=False)
        )
        result = await self.session.execute(
            update(PaymentCard)
            .where(PaymentCard.id == card_id, PaymentCard.user_id == user_id)
            .values(is_default=True)
            .returning(PaymentCard)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def create(self, card: PaymentCard) -> PaymentCard:
        self.session.add(card)
        await self.session.flush()
        return card

    async def mark_verified(self, card_id: int, now: datetime) -> PaymentCard | None:
        result = await self.session.execute(
            update(PaymentCard)
            .where(PaymentCard.id == card_id)
            .values(verified_at=now)
            .returning(PaymentCard)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def delete_all_for_user(self, user_id: int) -> Sequence[int]:
        """Account deletion removes stored cards outright.

        A soft-deleted account keeps its financial history, but a token that can
        still be charged is not history — it is a live credential.
        """
        result = await self.session.execute(
            delete(PaymentCard).where(PaymentCard.user_id == user_id).returning(PaymentCard.id)
        )
        await self.session.flush()
        return list(result.scalars().all())
