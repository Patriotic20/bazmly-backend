from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.staff.services import StaffService
from app.modules.venues.repositories import VenueTableRepository, VenueZoneRepository
from app.modules.venues.schemas import (
    TableCountsCreate,
    VenueTableRead,
    VenueZoneRead,
)

PERM_BRANCH_MANAGE = "branch.manage"


class VenueTableService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tables = VenueTableRepository(session)
        self.zones = VenueZoneRepository(session)
        self.staff = StaffService(session)

    async def list_for_venue(
        self, venue_id: int, zone_id: int | None = None
    ) -> Sequence[VenueTableRead]:
        rows = await self.tables.list_for_venue(venue_id, zone_id)
        return [VenueTableRead.model_validate(row) for row in rows]

    async def list_zones(self, venue_id: int) -> Sequence[VenueZoneRead]:
        rows = await self.zones.list_for_venue(venue_id)
        return [
            VenueZoneRead(
                id=row.id,
                slug=row.slug,
                name=row.name,
                sort_order=row.sort_order,
            )
            for row in rows
        ]

    async def create_from_counts(
        self, actor_user_id: int, venue_id: int, payload: TableCountsCreate
    ) -> Sequence[VenueTableRead]:
        """Expand onboarding's capacity buckets into numbered rows.

        The buckets are input, not state: booking needs numbered tables, so the
        counts are expanded once here and never stored.
        """
        await self.staff.require_permission_in_transaction(
            actor_user_id, venue_id, PERM_BRANCH_MANAGE
        )
        if payload.zone_id is not None:
            zone = await self.zones.get_by_id(payload.zone_id)
            if zone is None or zone.venue_id != venue_id:
                raise NotFoundError("Bu zona ushbu muassasaga tegishli emas")

        created = await self.tables.bulk_create_from_counts(
            venue_id, payload.counts, payload.zone_id
        )
        await self.session.commit()
        return [VenueTableRead.model_validate(row) for row in created]
