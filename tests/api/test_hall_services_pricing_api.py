"""A hall booking prices its services by their own unit, never by the client's say."""

from datetime import time, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.modules.services.models import VenueService
from app.modules.venue_groups.models import VenueGroup
from app.modules.venues.enums import VenueTypeSlug
from app.modules.venues.models import Venue, VenueGuestTier
from tests.api.conftest import auth_header
from tests.repositories import factories


async def hall(session: AsyncSession) -> tuple[VenueGroup, Venue]:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group, venue_type=VenueTypeSlug.TOYXONA)
    await factories.make_working_hours(session, venue, time(9, 0), time(23, 0))
    venue.min_advance_booking_days = 1
    session.add(VenueGuestTier(venue_id=venue.id, min_guests=100, max_guests=500, base_price=0))
    await session.flush()
    return group, venue


async def priced(session: AsyncSession, group: VenueGroup, price_unit: str) -> VenueService:
    catalog = await factories.make_service_catalog_entry(session)
    service = VenueService(
        venue_group_id=group.id,
        service_catalog_id=catalog.id,
        price=Decimal("150000"),
        currency="UZS",
        price_unit=price_unit,
        is_active=True,
        sort_order=0,
    )
    session.add(service)
    await session.flush()
    return service


def booking(venue: Venue, service: VenueService, quantity: int) -> dict[str, object]:
    return {
        "venue_id": venue.id,
        "booking_date": (utcnow_naive().date() + timedelta(days=7)).isoformat(),
        "start_time": "17:00:00",
        "end_time": "22:00:00",
        "guests_count": 300,
        "contact_name": "Mijoz",
        "contact_phone": "+998901112233",
        "services": [{"venue_service_id": service.id, "quantity": quantity}],
    }


async def test_a_per_guest_dasturxon_is_charged_for_every_guest(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The client says one plate; three hundred guests are three hundred plates."""
    group, venue = await hall(session)
    dasturxon = await priced(session, group, "per_guest")
    guest = await factories.make_user(session)

    response = await api_client.post(
        "/api/v1/bookings/hall", json=booking(venue, dasturxon, 1), headers=auth_header(guest.id)
    )

    assert response.status_code == 201, response.text
    assert Decimal(response.json()["booking"]["total_amount"]) == Decimal("45000000")


async def test_a_flat_service_is_charged_once(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    group, venue = await hall(session)
    video = await priced(session, group, "flat")
    guest = await factories.make_user(session)

    response = await api_client.post(
        "/api/v1/bookings/hall", json=booking(venue, video, 40), headers=auth_header(guest.id)
    )

    assert response.status_code == 201, response.text
    assert Decimal(response.json()["booking"]["total_amount"]) == Decimal("150000")


async def test_another_chains_service_cannot_be_booked(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    _group, venue = await hall(session)
    other_group, _other_venue = await hall(session)
    theirs = await priced(session, other_group, "flat")
    guest = await factories.make_user(session)

    response = await api_client.post(
        "/api/v1/bookings/hall", json=booking(venue, theirs, 1), headers=auth_header(guest.id)
    )

    assert response.status_code == 404
