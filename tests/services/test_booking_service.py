"""The rule-dense service: guards, price assembly, and translated conflicts."""

from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import (
    BookingNotCheckInableError,
    LeadTimeTooShortError,
    PermissionDeniedError,
    TableAlreadyBookedError,
)
from app.modules.bookings.enums import BookingStatus, PriceLineType
from app.modules.bookings.schemas import BookingItemCreate, TableReservationCreate
from app.modules.bookings.services import BookingService
from app.modules.venue_groups.models import VenueGroup
from app.modules.venues.models import Venue, VenueGuestTier, VenueTable
from tests.repositories import factories

CONTACT_NAME = "Test Guest"
CONTACT_PHONE = "+998901112233"


def future_day(days: int = 7) -> date:
    return utcnow_naive().date() + timedelta(days=days)


async def make_bookable_venue(
    session: AsyncSession, deposit_percent: str | None = None
) -> tuple[VenueGroup, Venue, VenueTable]:
    """An active venue, open all week, with one four-seat table."""
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    await factories.make_working_hours(session, venue, time(8, 0), time(23, 0))
    venue.min_advance_booking_days = 1
    if deposit_percent is not None:
        venue.requires_deposit = True
        venue.deposit_percent = Decimal(deposit_percent)
    await session.flush()
    table = await factories.make_table(session, venue, number=1, seats=4)
    return group, venue, table


async def test_lead_time_shorter_than_required_raises(session: AsyncSession) -> None:
    """`min_advance_booking_days` is the venue's notice period, enforced first."""
    _group, venue, table = await make_bookable_venue(session)
    venue.min_advance_booking_days = 3
    await session.flush()
    user = await factories.make_user(session)

    payload = TableReservationCreate(
        venue_id=venue.id,
        table_id=table.id,
        booking_date=future_day(1),
        start_time=time(19, 0),
        end_time=time(21, 0),
        guests_count=2,
        contact_name=CONTACT_NAME,
        contact_phone=CONTACT_PHONE,
    )

    with pytest.raises(LeadTimeTooShortError) as exc_info:
        await BookingService(session).create_table_reservation(user.id, payload, 1)

    assert exc_info.value.details is not None
    assert exc_info.value.details["required_days"] == 3


async def test_deposit_is_subtracted_from_the_total_not_added(
    session: AsyncSession,
) -> None:
    """Part 1 decision 7.

    A deposit is a portion of the price paid up front. Adding it would charge the
    guest twice for the same money, so the deposit line is negative and the total
    is unchanged by it.
    """
    group, venue, table = await make_bookable_venue(session, deposit_percent="30")
    language = await factories.get_language(session)
    item = await factories.make_menu_item(session, group, base_price=Decimal("100000.00"))
    await factories.make_menu_branch(session, item, venue)
    user = await factories.make_user(session)

    payload = TableReservationCreate(
        venue_id=venue.id,
        table_id=table.id,
        booking_date=future_day(),
        start_time=time(19, 0),
        end_time=time(21, 0),
        guests_count=2,
        items=[BookingItemCreate(menu_item_id=item.id, quantity=2)],
        contact_name=CONTACT_NAME,
        contact_phone=CONTACT_PHONE,
    )

    detail = await BookingService(session).create_table_reservation(user.id, payload, language.id)

    subtotal = Decimal("200000.00")
    assert detail.booking.subtotal == subtotal
    # The total is the subtotal: the deposit did not inflate it.
    assert detail.booking.total_amount == subtotal
    assert detail.booking.deposit_amount == Decimal("60000.00")

    deposit_lines = [line for line in detail.price_lines if line.line_type == PriceLineType.DEPOSIT]
    assert len(deposit_lines) == 1
    assert deposit_lines[0].amount == Decimal("-60000.00")


async def test_double_booking_surfaces_as_a_domain_error(session: AsyncSession) -> None:
    """The caller sees `TableAlreadyBookedError`, never `IntegrityError`.

    The repository lets the constraint speak; the service is what turns it into a
    business fact the API can render.
    """
    _group, venue, table = await make_bookable_venue(session)
    user = await factories.make_user(session)
    service = BookingService(session)
    day = future_day()

    first = TableReservationCreate(
        venue_id=venue.id,
        table_id=table.id,
        booking_date=day,
        start_time=time(18, 0),
        end_time=time(20, 0),
        guests_count=2,
        contact_name=CONTACT_NAME,
        contact_phone=CONTACT_PHONE,
    )
    await service.create_table_reservation(user.id, first, 1)

    overlapping = TableReservationCreate(
        venue_id=venue.id,
        table_id=table.id,
        booking_date=day,
        start_time=time(19, 0),
        end_time=time(21, 0),
        guests_count=2,
        contact_name=CONTACT_NAME,
        contact_phone=CONTACT_PHONE,
    )
    with pytest.raises(TableAlreadyBookedError):
        await service.create_table_reservation(user.id, overlapping, 1)


async def test_check_in_by_staff_of_another_venue_is_refused(
    session: AsyncSession,
) -> None:
    """The scanner must actually work at the branch the ticket belongs to."""
    _group, venue, table = await make_bookable_venue(session)
    user = await factories.make_user(session)
    service = BookingService(session)

    detail = await service.create_table_reservation(
        user.id,
        TableReservationCreate(
            venue_id=venue.id,
            table_id=table.id,
            booking_date=future_day(),
            start_time=time(18, 0),
            end_time=time(20, 0),
            guests_count=2,
            contact_name=CONTACT_NAME,
            contact_phone=CONTACT_PHONE,
        ),
        1,
    )
    await service.bookings.set_status(detail.booking.id, BookingStatus.CONFIRMED, utcnow_naive())
    await session.flush()

    other_group = await factories.make_venue_group(session)
    other_venue = await factories.make_venue(session, group=other_group)
    outsider = await factories.make_staff(session, other_venue, other_group)

    with pytest.raises(PermissionDeniedError):
        await service.check_in_by_qr(outsider.user_id, venue.id, detail.qr_token)


async def test_second_qr_scan_raises(session: AsyncSession) -> None:
    """The token is single-use: the second scan fails the `confirmed` guard."""
    group, venue, table = await make_bookable_venue(session)
    user = await factories.make_user(session)
    staff = await factories.make_staff(session, venue, group)
    service = BookingService(session)

    detail = await service.create_table_reservation(
        user.id,
        TableReservationCreate(
            venue_id=venue.id,
            table_id=table.id,
            booking_date=future_day(),
            start_time=time(18, 0),
            end_time=time(20, 0),
            guests_count=2,
            contact_name=CONTACT_NAME,
            contact_phone=CONTACT_PHONE,
        ),
        1,
    )
    await service.bookings.set_status(detail.booking.id, BookingStatus.CONFIRMED, utcnow_naive())
    await session.flush()

    checked_in = await service.check_in_by_qr(staff.user_id, venue.id, detail.qr_token)
    assert checked_in.status == BookingStatus.CHECKED_IN

    with pytest.raises(BookingNotCheckInableError):
        await service.check_in_by_qr(staff.user_id, venue.id, detail.qr_token)


async def test_table_too_small_for_the_party_raises(session: AsyncSession) -> None:
    from app.core.exceptions import CapacityExceededError

    _group, venue, table = await make_bookable_venue(session)
    user = await factories.make_user(session)

    payload = TableReservationCreate(
        venue_id=venue.id,
        table_id=table.id,
        booking_date=future_day(),
        start_time=time(19, 0),
        end_time=time(21, 0),
        guests_count=10,
        contact_name=CONTACT_NAME,
        contact_phone=CONTACT_PHONE,
    )

    with pytest.raises(CapacityExceededError):
        await BookingService(session).create_table_reservation(user.id, payload, 1)


async def test_hall_event_without_a_matching_tier_raises(session: AsyncSession) -> None:
    from app.core.exceptions import CapacityExceededError
    from app.modules.bookings.schemas import HallEventCreate

    _group, venue, _table = await make_bookable_venue(session)
    session.add(
        VenueGuestTier(
            venue_id=venue.id,
            min_guests=100,
            max_guests=150,
            base_price=Decimal("5000000.00"),
            sort_order=0,
        )
    )
    await session.flush()
    user = await factories.make_user(session)

    payload = HallEventCreate(
        venue_id=venue.id,
        booking_date=future_day(),
        start_time=time(12, 0),
        end_time=time(22, 0),
        guests_count=500,
        contact_name=CONTACT_NAME,
        contact_phone=CONTACT_PHONE,
    )

    with pytest.raises(CapacityExceededError):
        await BookingService(session).create_hall_event(user.id, payload, 1)
