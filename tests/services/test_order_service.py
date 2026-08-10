"""Closing a check is the rule that protects the revenue rollup."""

from datetime import time
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    PaymentIncompleteError,
    PermissionDeniedError,
    ReceiptAlreadyIssuedError,
    TableHasOpenOrderError,
)
from app.modules.menu.models import MenuItem
from app.modules.orders.enums import OrderPaymentMethod
from app.modules.orders.schemas import (
    OrderItemCreate,
    OrderOpen,
    OrderPaymentCreate,
)
from app.modules.orders.services import OrderService
from app.modules.staff.models import VenueStaff
from app.modules.venue_groups.models import VenueGroup
from app.modules.venues.models import Venue, VenueTable
from tests.repositories import factories

ITEM_PRICE = Decimal("50000.00")


async def setup_order_env(
    session: AsyncSession,
) -> tuple[VenueGroup, Venue, VenueTable, VenueStaff, MenuItem]:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    await factories.make_working_hours(session, venue, time(8, 0), time(23, 0))
    table = await factories.make_table(session, venue, number=1, seats=4)
    staff = await factories.make_staff(session, venue, group, role_slug="waiter")
    await factories.grant(session, "waiter", "orders.open", "orders.add_items", "orders.close")
    item = await factories.make_menu_item(session, group, base_price=ITEM_PRICE)
    await factories.make_menu_branch(session, item, venue)
    return group, venue, table, staff, item


async def test_opening_a_table_twice_is_a_domain_error(session: AsyncSession) -> None:
    """The partial unique index speaks; the service translates."""
    _group, venue, table, staff, _item = await setup_order_env(session)
    service = OrderService(session)
    payload = OrderOpen(table_id=table.id, guests_count=2)

    await service.open_table(staff.user_id, venue.id, payload)

    with pytest.raises(TableHasOpenOrderError):
        await service.open_table(staff.user_id, venue.id, payload)


async def test_opening_without_permission_is_refused(session: AsyncSession) -> None:
    """Failure is an error, never a silent no-op."""
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    table = await factories.make_table(session, venue)
    staff = await factories.make_staff(session, venue, group, role_slug="security")

    with pytest.raises(PermissionDeniedError):
        await OrderService(session).open_table(
            staff.user_id, venue.id, OrderOpen(table_id=table.id)
        )


async def test_closing_below_the_total_raises(session: AsyncSession) -> None:
    """Settles Part 2's open question 9.

    `venue_daily_stats.revenue` sums `order_payments`, so a check closed with no
    payment row — or a short one — would make the dashboard understate the day.
    """
    _group, venue, table, staff, item = await setup_order_env(session)
    service = OrderService(session)

    order = await service.open_table(
        staff.user_id, venue.id, OrderOpen(table_id=table.id, guests_count=2)
    )
    await service.add_items(
        staff.user_id,
        venue.id,
        order.id,
        [OrderItemCreate(menu_item_id=item.id, quantity=2)],
    )

    # No payment at all.
    with pytest.raises(PaymentIncompleteError):
        await service.close(staff.user_id, venue.id, order.id)

    # A part payment is still not enough.
    await service.add_payment(
        staff.user_id,
        venue.id,
        order.id,
        OrderPaymentCreate(method=OrderPaymentMethod.CASH, amount=Decimal("40000.00")),
    )
    with pytest.raises(PaymentIncompleteError) as exc_info:
        await service.close(staff.user_id, venue.id, order.id)

    assert exc_info.value.details is not None
    assert exc_info.value.details["outstanding"] == "60000.00"


async def test_closing_twice_raises_receipt_already_issued(
    session: AsyncSession,
) -> None:
    """A receipt is written once. A correction is a new order or a refund."""
    _group, venue, table, staff, item = await setup_order_env(session)
    service = OrderService(session)

    order = await service.open_table(
        staff.user_id, venue.id, OrderOpen(table_id=table.id, guests_count=2)
    )
    await service.add_items(
        staff.user_id,
        venue.id,
        order.id,
        [OrderItemCreate(menu_item_id=item.id, quantity=1)],
    )
    await service.add_payment(
        staff.user_id,
        venue.id,
        order.id,
        OrderPaymentCreate(method=OrderPaymentMethod.CASH, amount=ITEM_PRICE),
    )

    receipt = await service.close(staff.user_id, venue.id, order.id)
    assert receipt.reprinted_count == 0
    assert receipt.payload["total_amount"] == "50000.00"

    with pytest.raises(ReceiptAlreadyIssuedError):
        await service.close(staff.user_id, venue.id, order.id)


async def test_cash_is_a_valid_settlement(session: AsyncSession) -> None:
    """Cash settles a check exactly like a card would — what matters is that a
    payment row exists for the rollup to read."""
    _group, venue, table, staff, item = await setup_order_env(session)
    service = OrderService(session)

    order = await service.open_table(
        staff.user_id, venue.id, OrderOpen(table_id=table.id, guests_count=2)
    )
    await service.add_items(
        staff.user_id,
        venue.id,
        order.id,
        [OrderItemCreate(menu_item_id=item.id, quantity=3)],
    )
    await service.add_payment(
        staff.user_id,
        venue.id,
        order.id,
        OrderPaymentCreate(method=OrderPaymentMethod.CASH, amount=Decimal("150000.00")),
    )

    receipt = await service.close(staff.user_id, venue.id, order.id)
    assert receipt.order_id == order.id

    detail = await service.get_detail(order.id, venue.id)
    assert detail.paid_amount == Decimal("150000.00")
    assert detail.order.status == "completed"


async def test_board_includes_free_tables(session: AsyncSession) -> None:
    _group, venue, table, staff, _item = await setup_order_env(session)
    await factories.make_table(session, venue, number=2, seats=2)
    service = OrderService(session)

    await service.open_table(staff.user_id, venue.id, OrderOpen(table_id=table.id))
    board = await service.board(venue.id)

    by_number = {row.number: row for row in board}
    assert by_number[1].order is not None
    assert by_number[2].order is None
    assert by_number[1].order.elapsed_seconds >= 0
