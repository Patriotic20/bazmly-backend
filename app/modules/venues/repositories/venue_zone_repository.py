from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Subquery, case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.localization.models import Language
from app.modules.venues.models import VenueZone, VenueZoneTranslation


@dataclass(frozen=True, slots=True)
class VenueZoneRow:
    zone: VenueZone
    name: str


class VenueZoneRepository:
    """Zones are rows — "Umumiy" is a UI shortcut meaning no zone filter, so it is
    never returned here."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _translation_subquery(self, language_id: int) -> Subquery:
        priority = case(
            (VenueZoneTranslation.language_id == language_id, 0),
            (Language.code == "uz", 1),
            (Language.code == "en", 2),
            else_=3,
        )
        return (
            select(
                VenueZoneTranslation.zone_id.label("zone_id"),
                VenueZoneTranslation.name.label("name"),
            )
            .join(Language, Language.id == VenueZoneTranslation.language_id)
            .distinct(VenueZoneTranslation.zone_id)
            .order_by(VenueZoneTranslation.zone_id, priority)
            .subquery()
        )

    async def get_by_id(self, zone_id: int) -> VenueZone | None:
        result = await self.session.execute(select(VenueZone).where(VenueZone.id == zone_id))
        return result.scalar_one_or_none()

    async def list_for_venue(self, venue_id: int, language_id: int) -> Sequence[VenueZoneRow]:
        translations = self._translation_subquery(language_id)
        result = await self.session.execute(
            select(VenueZone, translations.c.name)
            .outerjoin(translations, translations.c.zone_id == VenueZone.id)
            .where(VenueZone.venue_id == venue_id, VenueZone.is_active.is_(True))
            .order_by(VenueZone.sort_order)
        )
        return [VenueZoneRow(zone=row[0], name=row[1] or row[0].slug) for row in result.all()]

    async def create(self, zone: VenueZone) -> VenueZone:
        self.session.add(zone)
        await self.session.flush()
        return zone

    async def add_translation(self, translation: VenueZoneTranslation) -> VenueZoneTranslation:
        self.session.add(translation)
        await self.session.flush()
        return translation
