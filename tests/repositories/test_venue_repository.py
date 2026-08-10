"""Search combines PostGIS distance, trigram name matching and a computed
`is_open_now` in one statement."""

from datetime import date, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.venues.models import VenueSpecialDay
from app.modules.venues.repositories import SORT_DISTANCE, VenueRepository
from tests.repositories import factories

# Amir Temur square, the reference point every distance below is measured from.
ORIGIN_LAT = 41.311081
ORIGIN_LON = 69.240562

# A Monday, inside 08:00-20:00 working hours.
LOCAL_NOON = datetime(2026, 8, 3, 12, 0)


async def test_search_orders_by_distance(session: AsyncSession) -> None:
    """Three venues at increasing distance come back nearest-first, with a
    `distance_m` that actually grows."""

    near = await factories.make_venue(
        session, name="Near", latitude=ORIGIN_LAT, longitude=ORIGIN_LON
    )
    middle = await factories.make_venue(
        session, name="Middle", latitude=ORIGIN_LAT + 0.01, longitude=ORIGIN_LON
    )
    far = await factories.make_venue(
        session, name="Far", latitude=ORIGIN_LAT + 0.05, longitude=ORIGIN_LON
    )

    page = await VenueRepository(session).search(
        local_dt=LOCAL_NOON,
        latitude=ORIGIN_LAT,
        longitude=ORIGIN_LON,
        sort=SORT_DISTANCE,
    )

    ids = [row.venue.id for row in page.items]
    assert ids == [near.id, middle.id, far.id]

    distances = [row.distance_m for row in page.items]
    assert all(d is not None for d in distances)
    assert distances[0] < distances[1] < distances[2]  # type: ignore[operator]
    assert page.total == 3


async def test_search_within_radius_excludes_far_venues(session: AsyncSession) -> None:
    """`ST_DWithin` is a filter; the total reflects it."""

    near = await factories.make_venue(
        session, name="Near", latitude=ORIGIN_LAT, longitude=ORIGIN_LON
    )
    await factories.make_venue(session, name="Far", latitude=ORIGIN_LAT + 0.5, longitude=ORIGIN_LON)

    page = await VenueRepository(session).search(
        local_dt=LOCAL_NOON,
        latitude=ORIGIN_LAT,
        longitude=ORIGIN_LON,
        radius_m=2000,
        sort=SORT_DISTANCE,
    )

    assert [row.venue.id for row in page.items] == [near.id]
    assert page.total == 1


async def test_is_open_now_is_false_when_a_special_day_closes_the_venue(
    session: AsyncSession,
) -> None:
    """The clock says open, the special day says closed, and the special day wins.

    This is the distinction the schema insists on: `venues.status` is
    administrative, `is_open_now` is the clock, and a holiday override sits on top
    of the clock rather than on the status.
    """
    venue = await factories.make_venue(session, name="Yunusobod")
    await factories.make_working_hours(session, venue, time(8, 0), time(20, 0))

    repository = VenueRepository(session)

    # Inside working hours, with no override.
    assert await repository.is_open_at(venue.id, LOCAL_NOON) is True

    session.add(
        VenueSpecialDay(
            venue_id=venue.id,
            date=date(2026, 8, 3),
            is_closed=True,
        )
    )
    await session.flush()

    assert await repository.is_open_at(venue.id, LOCAL_NOON) is False

    page = await repository.search(local_dt=LOCAL_NOON)
    row = next(item for item in page.items if item.venue.id == venue.id)
    # Still listed — closed is a badge, not an exclusion.
    assert row.is_open_now is False


async def test_search_can_filter_to_open_venues_only(session: AsyncSession) -> None:
    """`is_open_now` becomes a filter only when explicitly asked for."""

    open_venue = await factories.make_venue(session, name="Open")
    await factories.make_working_hours(session, open_venue, time(8, 0), time(20, 0))

    closed_venue = await factories.make_venue(session, name="Closed")
    await factories.make_working_hours(session, closed_venue, time(8, 0), time(20, 0))
    session.add(VenueSpecialDay(venue_id=closed_venue.id, date=date(2026, 8, 3), is_closed=True))
    await session.flush()

    repository = VenueRepository(session)

    unfiltered = await repository.search(local_dt=LOCAL_NOON)
    assert {row.venue.id for row in unfiltered.items} == {open_venue.id, closed_venue.id}

    filtered = await repository.search(local_dt=LOCAL_NOON, only_open_now=True)
    assert [row.venue.id for row in filtered.items] == [open_venue.id]


async def test_search_returns_the_name_off_the_venue_row(session: AsyncSession) -> None:
    """No join, no language fallback — `venues.name` is the only source.

    This replaces a test that exercised the `DISTINCT ON` translation fallback. That
    machinery is gone, so what is worth asserting now is that the name survives the
    search query at all: it is selected alongside computed columns like `distance_m`,
    which is where a column could quietly go missing.
    """
    venue = await factories.make_venue(session, name="Tinchlik Plaza")

    page = await VenueRepository(session).search(local_dt=LOCAL_NOON)

    row = next(item for item in page.items if item.venue.id == venue.id)
    assert row.name == "Tinchlik Plaza"
