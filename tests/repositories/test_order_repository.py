"""Table state is derived, and the races are settled in Postgres."""

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.orders.repositories import OrderRepository
from tests.repositories import factories

BUSINESS_DATE = factories.business_day()
OPENED_AT = datetime(2026, 8, 1, 18, 0)


async def test_open_for_table_twice_raises(session: AsyncSession) -> None:
    """Two waiters tapping the same empty table produce one check and one error.

    `one_open_order_per_table` is the authority — the repository deliberately does
    not pre-check, because a pre-check loses the race it is meant to win.
    """
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    table = await factories.make_table(session, venue)
    staff = await factories.make_staff(session, venue, group)
    repository = OrderRepository(session)

    await repository.open_for_table(
        venue_id=venue.id,
        table_id=table.id,
        staff_id=staff.id,
        business_date=BUSINESS_DATE,
        now=OPENED_AT,
    )

    with pytest.raises(IntegrityError) as exc_info:
        await repository.open_for_table(
            venue_id=venue.id,
            table_id=table.id,
            staff_id=staff.id,
            business_date=BUSINESS_DATE,
            now=OPENED_AT,
        )

    assert "one_open_order_per_table" in str(exc_info.value)


async def test_open_for_table_is_allowed_again_after_the_check_closes(
    session: AsyncSession,
) -> None:
    """The index is partial, so a completed order stops holding the table."""
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    table = await factories.make_table(session, venue)
    staff = await factories.make_staff(session, venue, group)
    repository = OrderRepository(session)

    first = await repository.open_for_table(
        venue_id=venue.id,
        table_id=table.id,
        staff_id=staff.id,
        business_date=BUSINESS_DATE,
        now=OPENED_AT,
    )
    from app.modules.orders.models import OrderStatus

    first.status = OrderStatus.SERVED
    await session.flush()
    assert await repository.close(first.id, staff.id, datetime(2026, 8, 1, 20, 0)) is not None

    second = await repository.open_for_table(
        venue_id=venue.id,
        table_id=table.id,
        staff_id=staff.id,
        business_date=BUSINESS_DATE,
        now=datetime(2026, 8, 1, 20, 30),
    )
    assert second.id != first.id


async def test_table_board_returns_every_active_table_including_empty_ones(
    session: AsyncSession,
) -> None:
    """The board is a left join, so a free table is a row with `order is None`.

    That is the whole reason there is no `venue_tables.state` column: nothing can
    disagree with the orders table.
    """
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    occupied = await factories.make_table(session, venue, number=1)
    await factories.make_table(session, venue, number=2)
    await factories.make_table(session, venue, number=3)
    inactive = await factories.make_table(session, venue, number=4)
    inactive.is_active = False
    await session.flush()

    staff = await factories.make_staff(session, venue, group)
    repository = OrderRepository(session)
    await repository.open_for_table(
        venue_id=venue.id,
        table_id=occupied.id,
        staff_id=staff.id,
        business_date=BUSINESS_DATE,
        now=OPENED_AT,
    )

    board = await repository.table_board(venue.id)

    assert [row.table.number for row in board] == [1, 2, 3]
    by_number = {row.table.number: row for row in board}
    assert by_number[1].order is not None
    assert by_number[2].order is None
    assert by_number[3].order is None


async def test_next_order_number_never_duplicates_across_two_sessions(
    committing_sessions: tuple[AsyncSession, AsyncSession],
) -> None:
    """Two connections numbering orders for the same branch and day.

    The `FOR UPDATE` lock on the venue row serialises them: the second caller
    blocks until the first commits, then reads the number the first actually used.
    A bare `MAX + 1` would let both read the same maximum and collide on
    `UNIQUE (venue_id, business_date, order_number)`.
    """
    first_session, second_session = committing_sessions

    group = await factories.make_venue_group(first_session)
    venue = await factories.make_venue(first_session, group=group)
    table_a = await factories.make_table(first_session, venue, number=1)
    table_b = await factories.make_table(first_session, venue, number=2)
    staff = await factories.make_staff(first_session, venue, group)
    await first_session.commit()

    venue_id, staff_id = venue.id, staff.id

    first_order = await OrderRepository(first_session).open_for_table(
        venue_id=venue_id,
        table_id=table_a.id,
        staff_id=staff_id,
        business_date=BUSINESS_DATE,
        now=OPENED_AT,
    )
    await first_session.commit()

    second_order = await OrderRepository(second_session).open_for_table(
        venue_id=venue_id,
        table_id=table_b.id,
        staff_id=staff_id,
        business_date=BUSINESS_DATE,
        now=OPENED_AT,
    )
    await second_session.commit()

    assert first_order.order_number == 1
    assert second_order.order_number == 2
    assert first_order.order_number != second_order.order_number
