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


async def make_staffed(
    session: AsyncSession, role_slug: str = "manager"
) -> tuple[Venue, VenueTable, User, User]:
    """A bookable branch plus an employee who can decide its requests.

    `manager` carries both `bookings.confirm` and `bookings.cancel` from the seed
    matrix, so nothing here has to grant permissions by hand.
    """
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    await factories.make_working_hours(session, venue, time(8, 0), time(23, 0))
    venue.min_advance_booking_days = 1
    await session.flush()
    table = await factories.make_table(session, venue, number=1, seats=4)
    guest = await factories.make_user(session)
    employment = await factories.make_staff(session, venue, group, role_slug)
    staff = await session.get(User, employment.user_id)
    assert staff is not None
    return venue, table, guest, staff


async def book(
    api_client: AsyncClient, venue: Venue, table: VenueTable, guest: User
) -> dict[str, object]:
    created = await api_client.post(
        "/api/v1/bookings/table",
        json=payload(venue.id, table.id, "18:00:00", "20:00:00"),
        headers=auth_header(guest.id),
    )
    assert created.status_code == 201, created.text
    body: dict[str, object] = created.json()
    assert body["booking"]["status"] == "pending"  # type: ignore[index]
    return body


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


async def test_confirming_a_request_lets_the_ticket_be_scanned(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The path this endpoint exists for, end to end.

    Check-in refuses anything that is not `confirmed`, and nothing else in the
    system produces that status — so before `confirm` existed, a guest's ticket
    could never be scanned no matter what either side did.
    """
    venue, table, guest, staff = await make_staffed(session)
    created = await book(api_client, venue, table, guest)
    booking_id = created["booking"]["id"]

    confirmed = await api_client.post(
        f"/api/v1/venue/bookings/{booking_id}/confirm?venue_id={venue.id}",
        headers=auth_header(staff.id),
    )

    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["confirmed_at"] is not None

    # `venue_id` goes in the query as well as the body: the permission guard
    # reads the query string, and a body it never looks at cannot satisfy it.
    scanned = await api_client.post(
        f"/api/v1/venue/bookings/check-in?venue_id={venue.id}",
        json={"venue_id": venue.id, "qr_token": created["qr_token"]},
        headers=auth_header(staff.id),
    )

    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["status"] == "checked_in"


async def test_rejecting_a_request_cancels_it(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """One terminal state, not two: a refusal lands where a guest's own
    cancellation lands, so every existing read already handles it."""
    venue, table, guest, staff = await make_staffed(session)
    created = await book(api_client, venue, table, guest)
    booking_id = created["booking"]["id"]

    rejected = await api_client.post(
        f"/api/v1/venue/bookings/{booking_id}/reject?venue_id={venue.id}",
        json={"reason": "Bu kunda zal band"},
        headers=auth_header(staff.id),
    )

    assert rejected.status_code == 200, rejected.text
    body = rejected.json()
    assert body["status"] == "cancelled"
    assert body["cancelled_at"] is not None

    mine = await api_client.get(f"/api/v1/bookings/{booking_id}", headers=auth_header(guest.id))
    assert mine.json()["booking"]["status"] == "cancelled"


async def test_a_request_is_decided_only_once(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Two employees opening the same list must not both be able to act."""
    venue, table, guest, staff = await make_staffed(session)
    created = await book(api_client, venue, table, guest)
    booking_id = created["booking"]["id"]
    url = f"/api/v1/venue/bookings/{booking_id}/confirm?venue_id={venue.id}"

    assert (await api_client.post(url, headers=auth_header(staff.id))).status_code == 200

    second = await api_client.post(url, headers=auth_header(staff.id))

    assert second.status_code == 422
    assert second.json()["code"] == "validation_failed"
    assert second.json()["details"]["status"] == "confirmed"


async def test_a_booking_at_another_branch_is_not_found(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """`venue_id` is what the permission check reads, so a mismatched pair must
    not leak whether the booking exists."""
    venue, table, guest, _ = await make_staffed(session)
    created = await book(api_client, venue, table, guest)

    other_venue, _, _, other_staff = await make_staffed(session)

    response = await api_client.post(
        f"/api/v1/venue/bookings/{created['booking']['id']}/confirm?venue_id={other_venue.id}",
        headers=auth_header(other_staff.id),
    )

    assert response.status_code == 404


async def test_deciding_without_a_venue_id_is_422(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The branch is a query parameter, not a path one. Omitting it is a
    validation failure rather than a permission failure — a 403 here would send
    a client hunting for the wrong bug."""
    venue, table, guest, staff = await make_staffed(session)
    created = await book(api_client, venue, table, guest)

    response = await api_client.post(
        f"/api/v1/venue/bookings/{created['booking']['id']}/confirm",
        headers=auth_header(staff.id),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


async def test_a_waiter_may_confirm_but_not_reject(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The two actions carry different permissions on purpose: taking a booking
    is front-of-house work, turning one away is not."""
    venue, table, guest, waiter = await make_staffed(session, role_slug="waiter")
    created = await book(api_client, venue, table, guest)
    booking_id = created["booking"]["id"]

    rejected = await api_client.post(
        f"/api/v1/venue/bookings/{booking_id}/reject?venue_id={venue.id}",
        json={"reason": "yo'q"},
        headers=auth_header(waiter.id),
    )
    assert rejected.status_code == 403

    confirmed = await api_client.post(
        f"/api/v1/venue/bookings/{booking_id}/confirm?venue_id={venue.id}",
        headers=auth_header(waiter.id),
    )
    assert confirmed.status_code == 200
