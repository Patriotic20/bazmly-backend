from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Subquery, case, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.engagement.models import Favorite
from app.modules.localization.models import Language
from app.modules.venues.models import Venue, VenueTranslation


@dataclass(frozen=True, slots=True)
class FavoriteVenueRow:
    favorite: Favorite
    venue: Venue
    name: str
    tagline: str | None


class FavoriteRepository:
    """The bookmark icon."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _translation_subquery(self, language_id: int) -> Subquery:
        priority = case(
            (VenueTranslation.language_id == language_id, 0),
            (Language.code == "uz", 1),
            (Language.code == "en", 2),
            else_=3,
        )
        return (
            select(
                VenueTranslation.venue_id.label("venue_id"),
                VenueTranslation.name.label("name"),
                VenueTranslation.tagline.label("tagline"),
            )
            .join(Language, Language.id == VenueTranslation.language_id)
            .distinct(VenueTranslation.venue_id)
            .order_by(VenueTranslation.venue_id, priority)
            .subquery()
        )

    async def exists(self, user_id: int, venue_id: int) -> bool:
        result = await self.session.execute(
            select(
                select(Favorite.id)
                .where(Favorite.user_id == user_id, Favorite.venue_id == venue_id)
                .exists()
            )
        )
        return bool(result.scalar_one())

    async def add(self, user_id: int, venue_id: int) -> Favorite:
        favorite = Favorite(user_id=user_id, venue_id=venue_id)
        self.session.add(favorite)
        await self.session.flush()
        return favorite

    async def remove(self, user_id: int, venue_id: int) -> None:
        await self.session.execute(
            delete(Favorite).where(Favorite.user_id == user_id, Favorite.venue_id == venue_id)
        )
        await self.session.flush()

    async def list_for_user(self, user_id: int, language_id: int) -> Sequence[FavoriteVenueRow]:
        translations = self._translation_subquery(language_id)
        result = await self.session.execute(
            select(Favorite, Venue, translations.c.name, translations.c.tagline)
            .join(Venue, Venue.id == Favorite.venue_id)
            .outerjoin(translations, translations.c.venue_id == Venue.id)
            .where(Favorite.user_id == user_id)
            .order_by(Favorite.created_at.desc())
        )
        return [
            FavoriteVenueRow(favorite=row[0], venue=row[1], name=row[2] or "", tagline=row[3])
            for row in result.all()
        ]
