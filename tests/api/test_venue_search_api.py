"""Search combines PostGIS distance with a computed is_open_now."""

from datetime import time

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.repositories import factories

ORIGIN_LAT = 41.311081
ORIGIN_LON = 69.240562


async def test_distance_is_present_and_ascending_when_coordinates_are_given(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """`lat`/`lng` turn on the distance sort and the distance_m field.

    The order has to come from `ST_Distance`, not from insertion order, so the
    venues are seeded nearest-last on purpose.
    """
    far = await factories.make_venue(
        session, name="Far", latitude=ORIGIN_LAT + 0.05, longitude=ORIGIN_LON
    )
    middle = await factories.make_venue(
        session, name="Middle", latitude=ORIGIN_LAT + 0.01, longitude=ORIGIN_LON
    )
    near = await factories.make_venue(
        session, name="Near", latitude=ORIGIN_LAT, longitude=ORIGIN_LON
    )

    response = await api_client.get(
        "/api/v1/venues/search",
        params={"lat": ORIGIN_LAT, "lng": ORIGIN_LON, "sort": "distance"},
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["id"] for item in items] == [near.id, middle.id, far.id]

    distances = [item["distance_m"] for item in items]
    assert all(d is not None for d in distances)
    assert distances == sorted(distances)


async def test_distance_is_null_without_coordinates(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await factories.make_venue(session, name="Somewhere")

    response = await api_client.get("/api/v1/venues/search")

    assert response.status_code == 200
    assert all(item["distance_m"] is None for item in response.json()["items"])


async def test_one_coordinate_alone_is_422(api_client: AsyncClient) -> None:
    """Half a point is a caller bug, not a partial answer: ignoring it would sort
    by rating while the app displays a distance sort."""
    response = await api_client.get("/api/v1/venues/search", params={"lat": ORIGIN_LAT})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


async def test_is_open_now_reflects_working_hours(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Closed venues stay in the list with the flag false — a Yopiq badge, not an
    exclusion."""
    open_venue = await factories.make_venue(session, name="Always open")
    await factories.make_working_hours(session, open_venue, time(0, 0), time(23, 59))

    closed_venue = await factories.make_venue(session, name="No hours set")

    response = await api_client.get("/api/v1/venues/search")

    assert response.status_code == 200
    by_id = {item["id"]: item for item in response.json()["items"]}
    assert by_id[open_venue.id]["is_open_now"] is True
    assert by_id[closed_venue.id]["is_open_now"] is False


async def test_search_is_paginated(api_client: AsyncClient, session: AsyncSession) -> None:
    for index in range(3):
        await factories.make_venue(session, name=f"Venue {index}")

    response = await api_client.get("/api/v1/venues/search", params={"limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["total"] >= 3
    assert body["limit"] == 2
