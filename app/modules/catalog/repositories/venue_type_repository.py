from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Subquery, case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import VenueType, VenueTypeTranslation
from app.modules.localization.models import Language


@dataclass(frozen=True, slots=True)
class VenueTypeRow:
    venue_type: VenueType
    name: str


class VenueTypeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _translation_subquery(self, language_id: int) -> Subquery:
        """One row per venue type: preferred language, else uz, else en.

        `DISTINCT ON` with a priority `CASE` resolves the fallback inside the
        query, so no caller ever receives every translation and picks in Python.
        """
        priority = case(
            (VenueTypeTranslation.language_id == language_id, 0),
            (Language.code == "uz", 1),
            (Language.code == "en", 2),
            else_=3,
        )
        return (
            select(
                VenueTypeTranslation.venue_type_id.label("venue_type_id"),
                VenueTypeTranslation.name.label("name"),
            )
            .join(Language, Language.id == VenueTypeTranslation.language_id)
            .distinct(VenueTypeTranslation.venue_type_id)
            .order_by(VenueTypeTranslation.venue_type_id, priority)
            .subquery()
        )

    async def get_by_id(self, venue_type_id: int) -> VenueType | None:
        result = await self.session.execute(select(VenueType).where(VenueType.id == venue_type_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> VenueType | None:
        result = await self.session.execute(select(VenueType).where(VenueType.slug == slug))
        return result.scalar_one_or_none()

    async def list_active(self, language_id: int) -> Sequence[VenueTypeRow]:
        translations = self._translation_subquery(language_id)
        result = await self.session.execute(
            select(VenueType, translations.c.name)
            .outerjoin(translations, translations.c.venue_type_id == VenueType.id)
            .where(VenueType.is_active.is_(True))
            .order_by(VenueType.sort_order)
        )
        return [VenueTypeRow(venue_type=row[0], name=row[1] or row[0].slug) for row in result.all()]
