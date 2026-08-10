# TODO(service): added by the API task — catalog had no service, but the
# amenity picker needs one so the endpoint does not reach into repositories.
# Recorded in DECISIONS.md.
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.repositories import AmenityRepository
from app.modules.catalog.schemas import AmenityRead


class CatalogService:
    """The platform-owned amenity picker. Read-only.

    Venue types used to be served from here too. They are a `VenueTypeSlug` enum
    now, shipped in the client, so there is no endpoint and no row to fetch.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.amenities = AmenityRepository(session)

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
