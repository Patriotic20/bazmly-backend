"""Turning a phone's coordinates into a tuman.

This is the first thing the app asks on entry, before a session exists, so the
route is public and has to answer for a visitor with no account at all. The
assertions run against the seeded register — all 209 districts — because the
answer is only useful if it agrees with the district a person would name.
"""

from httpx import AsyncClient

# Coordinates taken from the seeded venues, which sit in real places.
CHILONZOR = (41.2753, 69.2039)
YUNUSOBOD = (41.3516, 69.2897)
SAMARQAND = (39.6548, 66.9757)

# Berlin: a phone that is nowhere near Uzbekistan.
ABROAD = (52.5200, 13.4050)

# Half of Uzbekistan's width. Anything past this is not "the district you are in".
FAR_AWAY_M = 500_000


async def test_a_tashkent_coordinate_names_its_district(api_client: AsyncClient) -> None:
    lat, lng = CHILONZOR

    response = await api_client.get(f"/api/v1/districts/nearest?lat={lat}&lng={lng}")

    assert response.status_code == 200
    body = response.json()
    assert body["district_name"] == "Chilonzor tumani"
    assert body["region_name"] == "Toshkent shahri"


async def test_neighbouring_districts_are_told_apart(api_client: AsyncClient) -> None:
    """Two points 14 km apart in the same city must not collapse to one answer.

    This is the case the seeded district centres exist to serve, and the one a
    coarser method — nearest region, or a bounding box — would get wrong.
    """
    chilonzor = await api_client.get(
        f"/api/v1/districts/nearest?lat={CHILONZOR[0]}&lng={CHILONZOR[1]}"
    )
    yunusobod = await api_client.get(
        f"/api/v1/districts/nearest?lat={YUNUSOBOD[0]}&lng={YUNUSOBOD[1]}"
    )

    assert chilonzor.json()["district_id"] != yunusobod.json()["district_id"]
    assert yunusobod.json()["district_name"] == "Yunusobod tumani"


async def test_it_crosses_regions(api_client: AsyncClient) -> None:
    """Not scoped to Toshkent: a customer in Samarqand gets Samarqand."""
    lat, lng = SAMARQAND

    body = (await api_client.get(f"/api/v1/districts/nearest?lat={lat}&lng={lng}")).json()

    assert body["region_name"] == "Samarqand"
    assert body["distance_m"] < 5_000


async def test_the_distance_exposes_a_coordinate_from_abroad(api_client: AsyncClient) -> None:
    """A point outside the country still resolves — to something absurdly far.

    The route cannot refuse it without inventing a border, so it reports the
    distance instead and leaves the client to decide the answer is meaningless.
    """
    lat, lng = ABROAD

    body = (await api_client.get(f"/api/v1/districts/nearest?lat={lat}&lng={lng}")).json()

    assert body["distance_m"] > FAR_AWAY_M


async def test_it_answers_without_a_session(api_client: AsyncClient) -> None:
    """No Authorization header at all: the location is picked before sign-in."""
    lat, lng = CHILONZOR

    response = await api_client.get(f"/api/v1/districts/nearest?lat={lat}&lng={lng}")

    assert response.status_code == 200


async def test_impossible_coordinates_are_refused(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/districts/nearest?lat=999&lng=0")

    assert response.status_code == 422


async def test_both_coordinates_are_required(api_client: AsyncClient) -> None:
    """One alone is a mistake, not half an answer."""
    response = await api_client.get("/api/v1/districts/nearest?lat=41.2753")

    assert response.status_code == 422
