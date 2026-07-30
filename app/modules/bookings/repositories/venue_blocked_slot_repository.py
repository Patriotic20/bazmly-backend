from collections.abc import Sequence
from datetime import date as date_type

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bookings.models import VenueBlockedSlot


class VenueBlockedSlotRepository:
    """Manual closures that feed availability alongside working hours and bookings."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, slot_id: int) -> VenueBlockedSlot | None:
        result = await self.session.execute(
            select(VenueBlockedSlot).where(VenueBlockedSlot.id == slot_id)
        )
        return result.scalar_one_or_none()

    async def list_for_venue(
        self, venue_id: int, date_from: date_type, date_to: date_type
    ) -> Sequence[VenueBlockedSlot]:
        result = await self.session.execute(
            select(VenueBlockedSlot)
            .where(
                VenueBlockedSlot.venue_id == venue_id,
                VenueBlockedSlot.date >= date_from,
                VenueBlockedSlot.date <= date_to,
            )
            .order_by(VenueBlockedSlot.date, VenueBlockedSlot.start_time)
        )
        return result.scalars().all()

    async def create(self, slot: VenueBlockedSlot) -> VenueBlockedSlot:
        self.session.add(slot)
        await self.session.flush()
        return slot

    async def delete(self, slot_id: int) -> None:
        await self.session.execute(delete(VenueBlockedSlot).where(VenueBlockedSlot.id == slot_id))
        await self.session.flush()
