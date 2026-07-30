from collections.abc import Sequence
from datetime import date as date_type
from datetime import datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import (
    get_availability_cache,
    venue_availability_key,
)
from app.core.exceptions import NotFoundError
from app.modules.bookings.repositories import (
    BookingRepository,
    VenueBlockedSlotRepository,
)
from app.modules.bookings.schemas import AvailableTableRead, BlockedDatesRead
from app.modules.venues.repositories import VenueRepository, VenueTableRepository

AVAILABILITY_TTL_SECONDS = 300


class AvailabilityService:
    """Free slots are computed, never materialized.

    A pre-generated slots table would be millions of rows and stale the moment a
    booking lands. Availability derives from working hours, special days, tables,
    live bookings and blocked slots, and is cached briefly; `BookingService`
    invalidates the venue's prefix whenever it writes.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tables = VenueTableRepository(session)
        self.venues = VenueRepository(session)
        self.blocked = VenueBlockedSlotRepository(session)
        self.bookings = BookingRepository(session)
        self.cache = get_availability_cache()

    async def available_tables(
        self,
        venue_id: int,
        booking_date: date_type,
        start_time: time,
        end_time: time,
        min_seats: int = 1,
    ) -> Sequence[AvailableTableRead]:
        """Cached per venue, day and window.

        The cache key includes the window because two parties asking for different
        hours on the same day have genuinely different answers.
        """
        key = (
            f"{venue_availability_key(venue_id, booking_date.isoformat())}"
            f":{start_time.isoformat()}-{end_time.isoformat()}:{min_seats}"
        )
        cached = await self.cache.get(key)
        if cached is not None:
            return [AvailableTableRead.model_validate(row) for row in cached]

        tables = await self.tables.list_available(
            venue_id, booking_date, start_time, end_time, min_seats
        )
        rows = [AvailableTableRead.model_validate(table) for table in tables]
        await self.cache.set(key, [row.model_dump() for row in rows], AVAILABILITY_TTL_SECONDS)
        return rows

    async def blocked_dates(
        self, venue_id: int, date_from: date_type, date_to: date_type
    ) -> BlockedDatesRead:
        """The greyed-out chips: days a hall event already owns."""
        venue = await self.venues.get_by_id(venue_id)
        if venue is None:
            raise NotFoundError("Muassasa topilmadi")

        dates = await self.bookings.blocked_dates_for_venue(venue_id, date_from, date_to)
        return BlockedDatesRead(venue_id=venue_id, dates=list(dates))

    async def is_open_at(self, venue_id: int, booking_date: date_type, at: time) -> bool:
        return await self.venues.is_open_at(venue_id, datetime.combine(booking_date, at))
