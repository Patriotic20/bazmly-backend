# TODO(service): added by the API task — catalog had no service, but the
# venue-type and amenity pickers need one so the endpoints do not reach into
# repositories. Recorded in DECISIONS.md.
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.repositories import AmenityRepository, VenueTypeRepository
from app.modules.catalog.schemas import AmenityRead, VenueTypeRead


class CatalogService:
    """Platform-owned pickers: venue types and amenities. Read-only."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.venue_types = VenueTypeRepository(session)
        self.amenities = AmenityRepository(session)

    async def list_venue_types(self) -> Sequence[VenueTypeRead]:
        rows = await self.venue_types.list_active()
        return [
            VenueTypeRead(
                id=row.id,
                slug=row.slug,
                name=row.name,
                icon_url=row.icon_url,
                sort_order=row.sort_order,
            )
            for row in rows
        ]

    async def list_amenities(self) -> Sequence[AmenityRead]:
        rows = await self.amenities.list_active()
        return [
            AmenityRead(
                id=row.id,
                slug=row.slug,
                name=row.name,
                icon_url=row.icon_url,
                sort_order=row.sort_order,
            )
            for row in rows
        ]
