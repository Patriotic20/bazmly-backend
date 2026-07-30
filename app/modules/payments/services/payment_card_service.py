from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.payments.models import PaymentCard
from app.modules.payments.repositories import PaymentCardRepository
from app.modules.payments.schemas import PaymentCardCreate, PaymentCardRead


class PaymentCardService:
    """Only the provider's token is stored, never the PAN."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.cards = PaymentCardRepository(session)

    async def list_for_user(self, user_id: int) -> Sequence[PaymentCardRead]:
        rows = await self.cards.list_for_user(user_id)
        return [PaymentCardRead.model_validate(row) for row in rows]

    async def add(self, user_id: int, payload: PaymentCardCreate) -> PaymentCardRead:
        """First card becomes the default, so there is always exactly one."""
        existing = await self.cards.list_for_user(user_id)
        should_default = payload.is_default or not existing

        card = await self.cards.create(
            PaymentCard(
                user_id=user_id,
                provider=payload.provider,
                provider_token=payload.provider_token,
                brand=payload.brand,
                last_four=payload.last_four,
                holder_name=payload.holder_name,
                expiry_month=payload.expiry_month,
                expiry_year=payload.expiry_year,
                is_default=False,
            )
        )
        if should_default:
            await self.cards.set_default(user_id, card.id)
        await self.session.commit()

        refreshed = await self.cards.get_by_id(card.id)
        if refreshed is None:
            raise NotFoundError("Karta topilmadi")
        return PaymentCardRead.model_validate(refreshed)

    async def set_default(self, user_id: int, card_id: int) -> PaymentCardRead:
        """Clears the previous default in the same flush, so no reader ever sees
        two defaults or none."""
        updated = await self.cards.set_default(user_id, card_id)
        if updated is None:
            raise NotFoundError("Karta topilmadi")
        await self.session.commit()
        return PaymentCardRead.model_validate(updated)
