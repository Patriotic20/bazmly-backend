from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, time

from sqlalchemy import Subquery, case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bookings.models import (
    Booking,
    BookingItem,
    BookingKind,
    BookingPriceLine,
    BookingService,
    BookingStatus,
)
from app.modules.bookings.models.booking_status_history import BookingStatusHistory
from app.modules.localization.models import Language
from app.modules.venues.models import Venue, VenueTable, VenueTranslation

# The states in which a booking holds its table. Matches the exclusion constraint
# and the hall-event partial index; changing one without the others reopens the
# double-booking race the database is there to close.
ACTIVE_BOOKING_STATUSES = (
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.CHECKED_IN,
)


@dataclass(frozen=True, slots=True)
class UserBookingRow:
    """A card in the Joylar tab."""

    booking: Booking
    venue: Venue
    venue_name: str
    table: VenueTable | None


class BookingRepository:
    """Double booking is settled in Postgres, not here.

    `create_table_reservation` and `create_hall_event` let `IntegrityError` escape
    on `no_overlapping_table_bookings` and `one_hall_event_per_day` respectively.
    `find_overlapping` exists only so the service can render a friendly message
    first — it is a courtesy, never the authority, because two callers can both
    pass it and only one can pass the constraint.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _venue_translation_subquery(self, language_id: int) -> Subquery:
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
            )
            .join(Language, Language.id == VenueTranslation.language_id)
            .distinct(VenueTranslation.venue_id)
            .order_by(VenueTranslation.venue_id, priority)
            .subquery()
        )

    async def create_table_reservation(self, booking: Booking) -> Booking:
        """Restaurant reservation. Sets only the table columns.

        `reserved_range` is a generated column, so it is never assigned here — the
        database derives it from `booking_date + start_time/end_time`, which is
        also what the exclusion constraint indexes.
        """
        booking.kind = BookingKind.TABLE_RESERVATION
        booking.guest_tier_id = None
        self.session.add(booking)
        await self.session.flush()
        return booking

    async def create_hall_event(self, booking: Booking) -> Booking:
        """To'yxona event. Sets only the guest-tier columns; a hall is booked for
        the whole day, which the partial unique index enforces."""
        booking.kind = BookingKind.HALL_EVENT
        booking.table_id = None
        self.session.add(booking)
        await self.session.flush()
        return booking

    async def get_by_id(self, booking_id: int) -> Booking | None:
        result = await self.session.execute(select(Booking).where(Booking.id == booking_id))
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: int, language_id: int, statuses: Sequence[str] | None = None
    ) -> Sequence[UserBookingRow]:
        translations = self._venue_translation_subquery(language_id)
        stmt = (
            select(Booking, Venue, translations.c.name, VenueTable)
            .join(Venue, Venue.id == Booking.venue_id)
            .outerjoin(translations, translations.c.venue_id == Venue.id)
            .outerjoin(VenueTable, VenueTable.id == Booking.table_id)
            .where(Booking.user_id == user_id)
        )
        if statuses:
            stmt = stmt.where(Booking.status.in_(statuses))
        result = await self.session.execute(
            stmt.order_by(Booking.booking_date.desc(), Booking.start_time.desc())
        )
        return [
            UserBookingRow(booking=row[0], venue=row[1], venue_name=row[2] or "", table=row[3])
            for row in result.all()
        ]

    async def list_for_venue_day(
        self,
        venue_id: int,
        booking_date: date_type,
        statuses: Sequence[str] | None = None,
    ) -> Sequence[Booking]:
        """The owner's Kutilayotgan mijozlar queue. Uses the
        `(venue_id, booking_date, status)` index."""
        stmt = select(Booking).where(
            Booking.venue_id == venue_id, Booking.booking_date == booking_date
        )
        if statuses:
            stmt = stmt.where(Booking.status.in_(statuses))
        result = await self.session.execute(stmt.order_by(Booking.start_time, Booking.id))
        return result.scalars().all()

    async def find_overlapping(
        self,
        table_id: int,
        booking_date: date_type,
        start_time: time,
        end_time: time,
    ) -> Sequence[Booking]:
        """Pre-check for a readable error message. The constraint still decides."""
        result = await self.session.execute(
            select(Booking)
            .where(
                Booking.table_id == table_id,
                Booking.booking_date == booking_date,
                Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            )
            .order_by(Booking.start_time)
        )
        return result.scalars().all()

    async def get_by_qr_token(self, token: str) -> Booking | None:
        result = await self.session.execute(select(Booking).where(Booking.qr_token == token))
        return result.scalar_one_or_none()

    async def get_by_receipt_number(self, number: str) -> Booking | None:
        result = await self.session.execute(select(Booking).where(Booking.receipt_number == number))
        return result.scalar_one_or_none()

    async def check_in(self, booking_id: int, staff_id: int, now: datetime) -> Booking | None:
        """Guarded transition `confirmed → checked_in`.

        Returns `None` when the guard fails, so a double scan or a scan of a
        cancelled booking is a no-op rather than a second check-in.

        `staff_id` is recorded in `booking_status_history` because `bookings` has
        no `checked_in_by_user_id` column — see DECISIONS.md.
        """
        result = await self.session.execute(
            update(Booking)
            .where(Booking.id == booking_id, Booking.status == BookingStatus.CONFIRMED)
            .values(status=BookingStatus.CHECKED_IN, checked_in_at=now)
            .returning(Booking)
        )
        booking = result.scalars().one_or_none()
        if booking is None:
            return None

        self.session.add(
            BookingStatusHistory(
                booking_id=booking_id,
                from_status=BookingStatus.CONFIRMED,
                to_status=BookingStatus.CHECKED_IN,
                changed_by_user_id=staff_id,
            )
        )
        await self.session.flush()
        return booking

    async def check_out(self, booking_id: int, now: datetime) -> Booking | None:
        """Closes the visit. `seated_minutes` is written once, from the real
        interval, so "Umumiy o'tirildi" reads a stored number rather than
        recomputing from timestamps that may later be corrected."""
        result = await self.session.execute(
            select(Booking).where(
                Booking.id == booking_id, Booking.status == BookingStatus.CHECKED_IN
            )
        )
        booking = result.scalar_one_or_none()
        if booking is None:
            return None

        seated_minutes = (
            int((now - booking.checked_in_at).total_seconds() // 60)
            if booking.checked_in_at is not None
            else None
        )
        booking.checked_out_at = now
        booking.completed_at = now
        booking.seated_minutes = seated_minutes
        booking.status = BookingStatus.COMPLETED
        await self.session.flush()
        return booking

    async def expire_stale(self, now: datetime) -> Sequence[int]:
        """Confirmed bookings past their grace window become no-shows.

        Returns the affected ids so the service can queue notifications — a bulk
        UPDATE otherwise tells the caller nothing about who to notify.
        """
        result = await self.session.execute(
            update(Booking)
            .where(
                Booking.status == BookingStatus.CONFIRMED,
                Booking.auto_cancel_at.is_not(None),
                Booking.auto_cancel_at <= now,
            )
            .values(status=BookingStatus.NO_SHOW)
            .returning(Booking.id)
        )
        await self.session.flush()
        return list(result.scalars().all())

    async def blocked_dates_for_venue(
        self, venue_id: int, date_from: date_type, date_to: date_type
    ) -> Sequence[date_type]:
        """Dates already taken by a hall event — the greyed-out chips in the
        date picker. A hall is booked for the whole day, so one row blocks it."""
        result = await self.session.execute(
            select(Booking.booking_date)
            .where(
                Booking.venue_id == venue_id,
                Booking.kind == BookingKind.HALL_EVENT,
                Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                Booking.booking_date >= date_from,
                Booking.booking_date <= date_to,
            )
            .distinct()
            .order_by(Booking.booking_date)
        )
        return list(result.scalars().all())

    async def set_status(
        self, booking_id: int, status: str, now: datetime, reason: str | None = None
    ) -> Booking | None:
        values: dict[str, object] = {"status": status}
        if status == BookingStatus.CONFIRMED:
            values["confirmed_at"] = now
        elif status == BookingStatus.CANCELLED:
            values["cancelled_at"] = now
            values["cancel_reason"] = reason
        result = await self.session.execute(
            update(Booking).where(Booking.id == booking_id).values(**values).returning(Booking)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def add_items(
        self, booking_id: int, items: Sequence[BookingItem]
    ) -> Sequence[BookingItem]:
        """Menu pre-order lines. Callers snapshot price and name before calling."""
        for item in items:
            item.booking_id = booking_id
            self.session.add(item)
        await self.session.flush()
        return items

    async def list_items(self, booking_id: int) -> Sequence[BookingItem]:
        result = await self.session.execute(
            select(BookingItem).where(BookingItem.booking_id == booking_id).order_by(BookingItem.id)
        )
        return result.scalars().all()

    async def add_services(
        self, booking_id: int, services: Sequence[BookingService]
    ) -> Sequence[BookingService]:
        for service in services:
            service.booking_id = booking_id
            self.session.add(service)
        await self.session.flush()
        return services

    async def list_services(self, booking_id: int) -> Sequence[BookingService]:
        result = await self.session.execute(
            select(BookingService)
            .where(BookingService.booking_id == booking_id)
            .order_by(BookingService.id)
        )
        return result.scalars().all()

    async def add_price_lines(
        self, booking_id: int, lines: Sequence[BookingPriceLine]
    ) -> Sequence[BookingPriceLine]:
        """The Detailed Price Report, frozen at confirmation."""
        for line in lines:
            line.booking_id = booking_id
            self.session.add(line)
        await self.session.flush()
        return lines

    async def list_price_lines(self, booking_id: int) -> Sequence[BookingPriceLine]:
        result = await self.session.execute(
            select(BookingPriceLine)
            .where(BookingPriceLine.booking_id == booking_id)
            .order_by(BookingPriceLine.sort_order, BookingPriceLine.id)
        )
        return result.scalars().all()

    async def record_status_change(
        self,
        booking_id: int,
        from_status: str | None,
        to_status: str,
        changed_by_user_id: int | None = None,
        comment: str | None = None,
    ) -> BookingStatusHistory:
        entry = BookingStatusHistory(
            booking_id=booking_id,
            from_status=from_status,
            to_status=to_status,
            changed_by_user_id=changed_by_user_id,
            comment=comment,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry
