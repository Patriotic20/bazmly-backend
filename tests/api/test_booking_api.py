"""Constraint violations must reach the client as business facts, not 500s."""

from datetime import time, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.modules.auth.models import User
from app.modules.venues.models import Venue, VenueTable
from tests.api.conftest import auth_header
from tests.repositories import factories


def payload(venue_id: int, table_id: int, start: str, end: str) -> dict[str, object]:
    return {
        "venue_id": venue_id,
        "table_id": table_id,
        "booking_date": (utcnow_naive().date() + timedelta(days=7)).isoformat(),
        "start_time": start,
        "end_time": end,
        "guests_count": 2,
        "contact_name": "Test Guest",
        "contact_phone": "+998901112233",
    }


async def make_bookable(session: AsyncSession) -> tuple[Venue, VenueTable, User]:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    await factories.make_working_hours(session, venue, time(8, 0), time(23, 0))
    venue.min_advance_booking_days = 1
    await session.flush()
    table = await factories.make_table(session, venue, number=1, seats=4)
    user = await factories.make_user(session)
    return venue, table, user


async def test_double_booking_the_same_table_is_409(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The exclusion constraint reaches the client as `table_already_booked`.

    A 500 here would tell the app nothing and would look like an outage; the whole
    point of translating the `IntegrityError` is that the guest can be told the
    slot is taken.
    """
    venue, table, user = await make_bookable(session)
    headers = auth_header(user.id)

    first = await api_client.post(
        "/api/v1/bookings/table",
        json=payload(venue.id, table.id, "18:00:00", "20:00:00"),
        headers=headers,
    )
    assert first.status_code == 201, first.text

    second = await api_client.post(
        "/api/v1/bookings/table",
        json=payload(venue.id, table.id, "19:00:00", "21:00:00"),
        headers=headers,
    )

    assert second.status_code == 409
    body = second.json()
    assert body["code"] == "table_already_booked"
    assert "message" in body and "details" in body


async def test_lead_time_too_short_is_422(api_client: AsyncClient, session: AsyncSession) -> None:
    venue, table, user = await make_bookable(session)
    venue.min_advance_booking_days = 30
    await session.flush()

    response = await api_client.post(
        "/api/v1/bookings/table",
        json=payload(venue.id, table.id, "18:00:00", "20:00:00"),
        headers=auth_header(user.id),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "lead_time_too_short"


async def test_booking_detail_carries_the_qr_but_the_list_does_not(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """`qr_token` is a bearer credential for check-in: detail only, never a list."""
    venue, table, user = await make_bookable(session)
    headers = auth_header(user.id)

    created = await api_client.post(
        "/api/v1/bookings/table",
        json=payload(venue.id, table.id, "18:00:00", "20:00:00"),
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["qr_token"]

    listed = await api_client.get("/api/v1/bookings", headers=headers)
    assert listed.status_code == 200
    assert all("qr_token" not in item for item in listed.json())


async def test_another_users_booking_is_403(api_client: AsyncClient, session: AsyncSession) -> None:
    venue, table, user = await make_bookable(session)
    created = await api_client.post(
        "/api/v1/bookings/table",
        json=payload(venue.id, table.id, "18:00:00", "20:00:00"),
        headers=auth_header(user.id),
    )
    booking_id = created.json()["booking"]["id"]

    intruder = await factories.make_user(session)
    response = await api_client.get(
        f"/api/v1/bookings/{booking_id}", headers=auth_header(intruder.id)
    )

    assert response.status_code == 403


async def test_money_is_serialised_as_a_string(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """JSON has one numeric type and it is a binary float — money travels as text."""
    venue, table, user = await make_bookable(session)
    created = await api_client.post(
        "/api/v1/bookings/table",
        json=payload(venue.id, table.id, "18:00:00", "20:00:00"),
        headers=auth_header(user.id),
    )

    total = created.json()["booking"]["total_amount"]
    assert isinstance(total, str)
    assert Decimal(total) == Decimal("0.00")
