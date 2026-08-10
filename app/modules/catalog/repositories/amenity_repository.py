from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Amenity
from app.modules.venues.models import VenueAmenity


class AmenityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active(self) -> Sequence[Amenity]:
        result = await self.session.execute(select(Amenity).order_by(Amenity.sort_order))
        return list(result.scalars().all())

    async def list_for_venue(self, venue_id: int) -> Sequence[Amenity]:
        result = await self.session.execute(
            select(Amenity)
            .join(VenueAmenity, VenueAmenity.amenity_id == Amenity.id)
            .where(VenueAmenity.venue_id == venue_id)
            .order_by(Amenity.sort_order)
        )
        return list(result.scalars().all())

    async def set_for_venue(self, venue_id: int, amenity_ids: Sequence[int]) -> None:
        """Replace the venue's amenity set in one flush."""
        await self.session.execute(delete(VenueAmenity).where(VenueAmenity.venue_id == venue_id))
        for amenity_id in amenity_ids:
            self.session.add(VenueAmenity(venue_id=venue_id, amenity_id=amenity_id))
        await self.session.flush()
