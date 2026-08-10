"""Closing a check is the rule that protects the revenue rollup."""

from datetime import time
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.menu.models import MenuItem
from app.modules.staff.models import (
    VenueStaff,
)
from app.modules.venues.models import Venue, VenueTable
from tests.api.conftest import auth_header
from tests.repositories import factories

ITEM_PRICE = Decimal("50000.00")


async def make_order_env(
    session: AsyncSession,
) -> tuple[Venue, VenueTable, VenueStaff, MenuItem]:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    await factories.make_working_hours(session, venue, time(8, 0), time(23, 0))
    table = await factories.make_table(session, venue, number=1, seats=4)
    staff = await factories.make_staff(session, venue, group, role_slug="waiter")
    await factories.grant(session, "waiter", "orders.open", "orders.add_items", "orders.close")
    item = await factories.make_menu_item(session, group, base_price=ITEM_PRICE)
    await factories.make_menu_branch(session, item, venue)
    return venue, table, staff, item


async def test_closing_with_insufficient_payment_is_422(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """`venue_daily_stats.revenue` sums payment rows, so a short close would make
    the dashboard understate the day."""
    venue, table, staff, item = await make_order_env(session)
    headers = auth_header(staff.user_id)

    opened = await api_client.post(
        f"/api/v1/venue/orders?venue_id={venue.id}",
        json={"table_id": table.id, "guests_count": 2},
        headers=headers,
    )
    assert opened.status_code == 201, opened.text
    order_id = opened.json()["id"]

    added = await api_client.post(
        f"/api/v1/venue/orders/{order_id}/items?venue_id={venue.id}",
        json=[{"menu_item_id": item.id, "quantity": 2}],
        headers=headers,
    )
    assert added.status_code == 201, added.text

    unpaid = await api_client.post(
        f"/api/v1/venue/orders/{order_id}/close?venue_id={venue.id}", headers=headers
    )
    assert unpaid.status_code == 422
    assert unpaid.json()["code"] == "payment_incomplete"

    await api_client.post(
        f"/api/v1/venue/orders/{order_id}/payments?venue_id={venue.id}",
        json={"method": "cash", "amount": "40000.00"},
        headers=headers,
    )
    short = await api_client.post(
        f"/api/v1/venue/orders/{order_id}/close?venue_id={venue.id}", headers=headers
    )
    assert short.status_code == 422
    assert short.json()["details"]["outstanding"] == "60000.00"


async def test_full_payment_closes_and_a_second_close_is_409(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A receipt is written once; a correction is a new order or a refund."""
    venue, table, staff, item = await make_order_env(session)
    headers = auth_header(staff.user_id)

    order_id = (
        await api_client.post(
            f"/api/v1/venue/orders?venue_id={venue.id}",
            json={"table_id": table.id, "guests_count": 2},
            headers=headers,
        )
    ).json()["id"]
    await api_client.post(
        f"/api/v1/venue/orders/{order_id}/items?venue_id={venue.id}",
        json=[{"menu_item_id": item.id, "quantity": 1}],
        headers=headers,
    )
    await api_client.post(
        f"/api/v1/venue/orders/{order_id}/payments?venue_id={venue.id}",
        json={"method": "cash", "amount": "50000.00"},
        headers=headers,
    )

    closed = await api_client.post(
        f"/api/v1/venue/orders/{order_id}/close?venue_id={venue.id}", headers=headers
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["receipt_number"]

    again = await api_client.post(
        f"/api/v1/venue/orders/{order_id}/close?venue_id={venue.id}", headers=headers
    )
    assert again.status_code == 409
    assert again.json()["code"] == "receipt_already_issued"


async def test_opening_the_same_table_twice_is_409(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    venue, table, staff, _item = await make_order_env(session)
    headers = auth_header(staff.user_id)
    body = {"table_id": table.id, "guests_count": 2}

    first = await api_client.post(
        f"/api/v1/venue/orders?venue_id={venue.id}", json=body, headers=headers
    )
    assert first.status_code == 201

    second = await api_client.post(
        f"/api/v1/venue/orders?venue_id={venue.id}", json=body, headers=headers
    )
    assert second.status_code == 409
    assert second.json()["code"] == "table_has_open_order"


async def test_table_board_shows_free_tables(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    venue, table, staff, _item = await make_order_env(session)
    await factories.make_table(session, venue, number=2, seats=2)
    headers = auth_header(staff.user_id)

    await api_client.post(
        f"/api/v1/venue/orders?venue_id={venue.id}",
        json={"table_id": table.id},
        headers=headers,
    )
    board = await api_client.get(
        f"/api/v1/venue/orders/table-board?venue_id={venue.id}", headers=headers
    )

    assert board.status_code == 200
    rows = {row["number"]: row for row in board.json()}
    assert rows[1]["order"] is not None
    assert rows[2]["order"] is None
