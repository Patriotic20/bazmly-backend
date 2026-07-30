"""The database, not the service, is the authority on double booking."""

from datetime import date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bookings.models import Booking, BookingKind, BookingStatus
from app.modules.bookings.repositories import BookingRepository
from app.modules.venues.models import VenueGuestTier
from tests.repositories import factories

BOOKING_DATE = date(2026, 8, 1)


def build_booking(
    *,
    user_id: int,
    venue_id: int,
    kind: str,
    start_time: time,
    end_time: time,
    status: str = BookingStatus.CONFIRMED,
    table_id: int | None = None,
    guest_tier_id: int | None = None,
    booking_date: date = BOOKING_DATE,
) -> Booking:
    suffix = factories.unique_suffix()
    return Booking(
        user_id=user_id,
        venue_id=venue_id,
        kind=kind,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        guests_count=4,
        status=status,
        contact_name="Test Guest",
        contact_phone="+998900000000",
        subtotal=Decimal("0"),
        discount_amount=Decimal("0"),
        deposit_amount=Decimal("0"),
        total_amount=Decimal("0"),
        currency="UZS",
        receipt_number=f"R-{suffix}",
        ticket_code=f"T-{suffix}"[:16],
        qr_token=f"Q-{suffix}",
        table_id=table_id,
        guest_tier_id=guest_tier_id,
    )


async def test_overlapping_table_booking_raises_integrity_error(
    session: AsyncSession,
) -> None:
    """The exclusion constraint, not a Python pre-check, is what stops it."""
    venue = await factories.make_venue(session)
    table = await factories.make_table(session, venue)
    user = await factories.make_user(session)
    repository = BookingRepository(session)

    await repository.create_table_reservation(
        build_booking(
            user_id=user.id,
            venue_id=venue.id,
            kind=BookingKind.TABLE_RESERVATION,
            start_time=time(18, 0),
            end_time=time(20, 0),
            table_id=table.id,
        )
    )

    with pytest.raises(IntegrityError) as exc_info:
        await repository.create_table_reservation(
            build_booking(
                user_id=user.id,
                venue_id=venue.id,
                kind=BookingKind.TABLE_RESERVATION,
                start_time=time(19, 0),
                end_time=time(21, 0),
                table_id=table.id,
            )
        )

    # The repository must not hide which constraint fired.
    assert "no_overlapping_table_bookings" in str(exc_info.value)


async def test_adjacent_table_bookings_are_allowed(session: AsyncSession) -> None:
    """A booking ending at 20:00 does not collide with one starting at 20:00 —
    `tsrange` is half-open, so the guard is not accidentally too strict."""
    venue = await factories.make_venue(session)
    table = await factories.make_table(session, venue)
    user = await factories.make_user(session)
    repository = BookingRepository(session)

    await repository.create_table_reservation(
        build_booking(
            user_id=user.id,
            venue_id=venue.id,
            kind=BookingKind.TABLE_RESERVATION,
            start_time=time(18, 0),
            end_time=time(20, 0),
            table_id=table.id,
        )
    )
    second = await repository.create_table_reservation(
        build_booking(
            user_id=user.id,
            venue_id=venue.id,
            kind=BookingKind.TABLE_RESERVATION,
            start_time=time(20, 0),
            end_time=time(22, 0),
            table_id=table.id,
        )
    )

    assert second.id is not None


async def test_concurrent_hall_events_for_one_day_leave_one_survivor(
    committing_sessions: tuple[AsyncSession, AsyncSession],
) -> None:
    """Two real connections race for the same venue and date.

    `one_hall_event_per_day` is a partial unique index, so the second writer is
    rejected rather than both being accepted. This needs two committed
    transactions: a savepoint inside one transaction is invisible to the other
    connection, so a single-session version would prove nothing about the race.
    """
    first_session, second_session = committing_sessions

    venue = await factories.make_venue(first_session)
    tier = VenueGuestTier(
        venue_id=venue.id,
        min_guests=100,
        max_guests=150,
        base_price=Decimal("1000000.00"),
        sort_order=0,
    )
    first_session.add(tier)
    await first_session.flush()
    user = await factories.make_user(first_session)
    await first_session.commit()

    venue_id, tier_id, user_id = venue.id, tier.id, user.id

    await BookingRepository(first_session).create_hall_event(
        build_booking(
            user_id=user_id,
            venue_id=venue_id,
            kind=BookingKind.HALL_EVENT,
            start_time=time(10, 0),
            end_time=time(23, 0),
            guest_tier_id=tier_id,
        )
    )
    await first_session.commit()

    with pytest.raises(IntegrityError) as exc_info:
        await BookingRepository(second_session).create_hall_event(
            build_booking(
                user_id=user_id,
                venue_id=venue_id,
                kind=BookingKind.HALL_EVENT,
                start_time=time(12, 0),
                end_time=time(22, 0),
                guest_tier_id=tier_id,
            )
        )

    assert "one_hall_event_per_day" in str(exc_info.value)

    # Exactly one survived.
    surviving = await first_session.execute(
        select(func.count()).select_from(Booking).where(Booking.venue_id == venue_id)
    )
    assert surviving.scalar_one() == 1


async def test_check_in_returns_none_when_booking_is_not_confirmed(
    session: AsyncSession,
) -> None:
    """A pending booking cannot be checked in, and the guard says so by returning
    `None` rather than raising or silently transitioning."""
    venue = await factories.make_venue(session)
    table = await factories.make_table(session, venue)
    user = await factories.make_user(session)
    staff_group = await factories.make_venue_group(session)
    staff = await factories.make_staff(session, venue, staff_group)
    repository = BookingRepository(session)

    booking = await repository.create_table_reservation(
        build_booking(
            user_id=user.id,
            venue_id=venue.id,
            kind=BookingKind.TABLE_RESERVATION,
            start_time=time(18, 0),
            end_time=time(20, 0),
            table_id=table.id,
            status=BookingStatus.PENDING,
        )
    )

    result = await repository.check_in(booking.id, staff.user_id, datetime(2026, 8, 1, 18, 5))

    assert result is None


async def test_check_in_transitions_a_confirmed_booking(session: AsyncSession) -> None:
    venue = await factories.make_venue(session)
    table = await factories.make_table(session, venue)
    user = await factories.make_user(session)
    staff_group = await factories.make_venue_group(session)
    staff = await factories.make_staff(session, venue, staff_group)
    repository = BookingRepository(session)

    booking = await repository.create_table_reservation(
        build_booking(
            user_id=user.id,
            venue_id=venue.id,
            kind=BookingKind.TABLE_RESERVATION,
            start_time=time(18, 0),
            end_time=time(20, 0),
            table_id=table.id,
            status=BookingStatus.CONFIRMED,
        )
    )
    now = datetime(2026, 8, 1, 18, 5)

    checked_in = await repository.check_in(booking.id, staff.user_id, now)

    assert checked_in is not None
    assert checked_in.status == BookingStatus.CHECKED_IN
    assert checked_in.checked_in_at == now

    # A second scan is a no-op, not a second check-in.
    assert await repository.check_in(booking.id, staff.user_id, now) is None
