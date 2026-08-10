from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.engagement.repositories import FavoriteRepository
from app.modules.engagement.schemas import FavoriteRead, FavoriteToggled
from app.modules.venues.enums import VenueStatus
from app.modules.venues.repositories import VenueRepository
from app.modules.venues.schemas import VenueListItem


class FavoriteService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.favorites = FavoriteRepository(session)
        self.venues = VenueRepository(session)

    async def toggle(self, user_id: int, venue_id: int) -> FavoriteToggled:
        """The bookmark icon is a toggle, so this is one idempotent endpoint
        rather than an add and a remove that can disagree about current state."""
        venue = await self.venues.get_by_id(venue_id)
        if venue is None:
            raise NotFoundError("Muassasa topilmadi")

        if await self.favorites.exists(user_id, venue_id):
            await self.favorites.remove(user_id, venue_id)
            is_favorite = False
        else:
            await self.favorites.add(user_id, venue_id)
            is_favorite = True

        await self.session.commit()
        return FavoriteToggled(venue_id=venue_id, is_favorite=is_favorite)

    async def list_for_user(self, user_id: int) -> Sequence[FavoriteRead]:
        rows = await self.favorites.list_for_user(user_id)
        return [
            FavoriteRead(
                id=row.favorite.id,
                venue=VenueListItem(
                    id=row.venue.id,
                    name=row.name,
                    tagline=row.tagline,
                    status=VenueStatus(row.venue.status),
                    rating_avg=row.venue.rating_avg,
                    reviews_count=row.venue.reviews_count,
                    base_price=row.venue.base_price,
                    currency=row.venue.currency,
                    discount_percent=row.venue.discount_percent,
                    requires_deposit=row.venue.requires_deposit,
                ),
            )
            for row in rows
        ]
