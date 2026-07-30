from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Subquery, case, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Amenity, AmenityTranslation
from app.modules.localization.models import Language
from app.modules.venues.models import VenueAmenity


@dataclass(frozen=True, slots=True)
class AmenityRow:
    amenity: Amenity
    name: str


class AmenityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _translation_subquery(self, language_id: int) -> Subquery:
        """One row per amenity: preferred language, else uz, else en."""
        priority = case(
            (AmenityTranslation.language_id == language_id, 0),
            (Language.code == "uz", 1),
            (Language.code == "en", 2),
            else_=3,
        )
        return (
            select(
                AmenityTranslation.amenity_id.label("amenity_id"),
                AmenityTranslation.name.label("name"),
            )
            .join(Language, Language.id == AmenityTranslation.language_id)
            .distinct(AmenityTranslation.amenity_id)
            .order_by(AmenityTranslation.amenity_id, priority)
            .subquery()
        )

    async def list_active(self, language_id: int) -> Sequence[AmenityRow]:
        translations = self._translation_subquery(language_id)
        result = await self.session.execute(
            select(Amenity, translations.c.name)
            .outerjoin(translations, translations.c.amenity_id == Amenity.id)
            .order_by(Amenity.sort_order)
        )
        return [AmenityRow(amenity=row[0], name=row[1] or row[0].slug) for row in result.all()]

    async def list_for_venue(self, venue_id: int, language_id: int) -> Sequence[AmenityRow]:
        translations = self._translation_subquery(language_id)
        result = await self.session.execute(
            select(Amenity, translations.c.name)
            .join(VenueAmenity, VenueAmenity.amenity_id == Amenity.id)
            .outerjoin(translations, translations.c.amenity_id == Amenity.id)
            .where(VenueAmenity.venue_id == venue_id)
            .order_by(Amenity.sort_order)
        )
        return [AmenityRow(amenity=row[0], name=row[1] or row[0].slug) for row in result.all()]

    async def set_for_venue(self, venue_id: int, amenity_ids: Sequence[int]) -> None:
        """Replace the venue's amenity set in one flush."""
        await self.session.execute(delete(VenueAmenity).where(VenueAmenity.venue_id == venue_id))
        for amenity_id in amenity_ids:
            self.session.add(VenueAmenity(venue_id=venue_id, amenity_id=amenity_id))
        await self.session.flush()
