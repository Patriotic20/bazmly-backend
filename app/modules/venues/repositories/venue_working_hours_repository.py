from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.venues.models import VenueWorkingHours


class VenueWorkingHoursRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_venue(self, venue_id: int) -> Sequence[VenueWorkingHours]:
        result = await self.session.execute(
            select(VenueWorkingHours)
            .where(VenueWorkingHours.venue_id == venue_id)
            .order_by(VenueWorkingHours.weekday)
        )
        return result.scalars().all()

    async def replace_all(
        self, venue_id: int, rows: Sequence[VenueWorkingHours]
    ) -> Sequence[VenueWorkingHours]:
        """Delete then reinsert in one flush.

        Onboarding collects one start/end plus a set of weekdays and writes seven
        rows; editing rewrites the whole week rather than diffing days, so a
        removed day cannot survive as a stale row.
        """
        await self.session.execute(
            delete(VenueWorkingHours).where(VenueWorkingHours.venue_id == venue_id)
        )
        for row in rows:
            row.venue_id = venue_id
            self.session.add(row)
        await self.session.flush()
        return rows
