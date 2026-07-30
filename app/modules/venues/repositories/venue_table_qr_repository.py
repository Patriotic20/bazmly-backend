from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.venues.models import Venue, VenueTable, VenueTableQr


@dataclass(frozen=True, slots=True)
class TableQrContext:
    """Everything the scan endpoint needs: which table, at which venue."""

    qr: VenueTableQr
    table: VenueTable
    venue: Venue


class VenueTableQrRepository:
    """The printed standee scanned *by* the customer. The opposite direction from
    `bookings.qr_token`, which the customer shows *to* the venue."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_token(self, token: str) -> TableQrContext | None:
        result = await self.session.execute(
            select(VenueTableQr, VenueTable, Venue)
            .join(VenueTable, VenueTable.id == VenueTableQr.table_id)
            .join(Venue, Venue.id == VenueTable.venue_id)
            .where(VenueTableQr.token == token, VenueTableQr.revoked_at.is_(None))
        )
        row = result.one_or_none()
        if row is None:
            return None
        return TableQrContext(qr=row[0], table=row[1], venue=row[2])

    async def create(self, qr: VenueTableQr) -> VenueTableQr:
        self.session.add(qr)
        await self.session.flush()
        return qr

    async def revoke(self, qr_id: int, now: datetime) -> VenueTableQr | None:
        result = await self.session.execute(
            update(VenueTableQr)
            .where(VenueTableQr.id == qr_id, VenueTableQr.revoked_at.is_(None))
            .values(revoked_at=now)
            .returning(VenueTableQr)
        )
        await self.session.flush()
        return result.scalars().one_or_none()
