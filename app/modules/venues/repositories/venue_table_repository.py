from collections.abc import Mapping, Sequence
from datetime import date as date_type
from datetime import time

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bookings.models import Booking, BookingStatus, VenueBlockedSlot
from app.modules.venues.models import VenueTable

# A table is unavailable while a booking in any of these states holds it.
BLOCKING_BOOKING_STATUSES = (
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.CHECKED_IN,
)


class VenueTableRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, table_id: int) -> VenueTable | None:
        result = await self.session.execute(select(VenueTable).where(VenueTable.id == table_id))
        return result.scalar_one_or_none()

    async def list_for_venue(
        self, venue_id: int, zone_id: int | None = None
    ) -> Sequence[VenueTable]:
        stmt = select(VenueTable).where(
            VenueTable.venue_id == venue_id, VenueTable.is_active.is_(True)
        )
        if zone_id is not None:
            stmt = stmt.where(VenueTable.zone_id == zone_id)
        result = await self.session.execute(stmt.order_by(VenueTable.number))
        return result.scalars().all()

    async def bulk_create_from_counts(
        self,
        venue_id: int,
        counts: Mapping[int, int],
        zone_id: int | None = None,
    ) -> Sequence[VenueTable]:
        """Expand onboarding's capacity buckets into numbered rows.

        `{2: 4, 4: 6}` becomes four two-seat tables and six four-seat ones. The
        buckets are input, not state, and are never stored. Numbering continues
        from the venue's current maximum so a second call does not collide with the
        `UNIQUE (venue_id, number)`.
        """
        result = await self.session.execute(
            select(func.coalesce(func.max(VenueTable.number), 0)).where(
                VenueTable.venue_id == venue_id
            )
        )
        next_number = int(result.scalar_one()) + 1

        created: list[VenueTable] = []
        for seats in sorted(counts):
            for _ in range(counts[seats]):
                table = VenueTable(
                    venue_id=venue_id,
                    number=next_number,
                    seats=seats,
                    zone_id=zone_id,
                    is_active=True,
                )
                self.session.add(table)
                created.append(table)
                next_number += 1

        await self.session.flush()
        return created

    async def list_available(
        self,
        venue_id: int,
        booking_date: date_type,
        start_time: time,
        end_time: time,
        min_seats: int = 1,
    ) -> Sequence[VenueTable]:
        """Active tables with neither an overlapping booking nor a blocked slot.

        Overlap is the half-open `start < other_end AND end > other_start`, so a
        booking ending at 20:00 does not collide with one starting at 20:00.

        `booking_date` / `start_time` are naive local venue values, never UTC.
        """
        overlapping_booking = (
            select(Booking.id)
            .where(
                Booking.table_id == VenueTable.id,
                Booking.booking_date == booking_date,
                Booking.status.in_(BLOCKING_BOOKING_STATUSES),
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            )
            .correlate(VenueTable)
            .exists()
        )

        blocked_slot = (
            select(VenueBlockedSlot.id)
            .where(
                or_(
                    VenueBlockedSlot.table_id == VenueTable.id,
                    and_(
                        VenueBlockedSlot.table_id.is_(None),
                        VenueBlockedSlot.venue_id == VenueTable.venue_id,
                    ),
                ),
                VenueBlockedSlot.date == booking_date,
                VenueBlockedSlot.start_time < end_time,
                VenueBlockedSlot.end_time > start_time,
            )
            .correlate(VenueTable)
            .exists()
        )

        result = await self.session.execute(
            select(VenueTable)
            .where(
                VenueTable.venue_id == venue_id,
                VenueTable.is_active.is_(True),
                VenueTable.seats >= min_seats,
                ~overlapping_booking,
                ~blocked_slot,
            )
            .order_by(VenueTable.seats, VenueTable.number)
        )
        return result.scalars().all()

    async def create(self, table: VenueTable) -> VenueTable:
        self.session.add(table)
        await self.session.flush()
        return table
