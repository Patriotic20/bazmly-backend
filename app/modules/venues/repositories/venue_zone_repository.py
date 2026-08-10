from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.venues.models import VenueZone


class VenueZoneRepository:
    """Zones are rows — "Umumiy" is a UI shortcut meaning no zone filter, so it is
    never returned here."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, zone_id: int) -> VenueZone | None:
        result = await self.session.execute(select(VenueZone).where(VenueZone.id == zone_id))
        return result.scalar_one_or_none()

    async def list_for_venue(self, venue_id: int) -> Sequence[VenueZone]:
        result = await self.session.execute(
            select(VenueZone)
            .where(VenueZone.venue_id == venue_id, VenueZone.is_active.is_(True))
            .order_by(VenueZone.sort_order)
        )
        return list(result.scalars().all())

    async def create(self, zone: VenueZone) -> VenueZone:
        self.session.add(zone)
        await self.session.flush()
        return zone
