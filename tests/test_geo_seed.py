"""The seeded geography is reference data, so it is asserted like reference data.

`venues.district_id` is NOT NULL and the region picker is the first screen a
customer sees, so an empty or half-applied seed is a broken product rather than a
missing nicety. These run against whatever `alembic upgrade head` produced.
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.geo.models import District, Region

# The register: 12 viloyat, Qoraqalpog'iston, and Toshkent shahri.
EXPECTED_REGIONS = 14
EXPECTED_DISTRICTS = 209

# Uzbekistan's bounding box, wide enough to hold Mo'ynoq and Termiz both.
MIN_LATITUDE = Decimal("37.1")
MAX_LATITUDE = Decimal("45.7")
MIN_LONGITUDE = Decimal("55.9")
MAX_LONGITUDE = Decimal("73.2")


async def test_every_region_is_seeded(session: AsyncSession) -> None:
    result = await session.execute(select(func.count()).select_from(Region))
    assert result.scalar_one() >= EXPECTED_REGIONS


async def test_region_codes_are_iso_3166_2(session: AsyncSession) -> None:
    """`RegionCreate` validates `^UZ-[A-Z]{2}$`; the seed has to agree with it."""
    result = await session.execute(select(Region.code).where(Region.code.like("UZ-%")))
    codes = set(result.scalars())

    assert {"UZ-TK", "UZ-TO", "UZ-QR", "UZ-SA", "UZ-FA"} <= codes
    assert len(codes) >= EXPECTED_REGIONS


async def test_tashkent_city_and_region_are_separate_rows(session: AsyncSession) -> None:
    """Two rows both called Toshkent would be indistinguishable in a picker."""
    result = await session.execute(
        select(Region.code, Region.name).where(Region.code.in_(["UZ-TK", "UZ-TO"]))
    )
    names = dict(result.all())

    assert names == {"UZ-TK": "Toshkent shahri", "UZ-TO": "Toshkent"}


async def test_every_district_is_seeded(session: AsyncSession) -> None:
    result = await session.execute(select(func.count()).select_from(District))
    assert result.scalar_one() >= EXPECTED_DISTRICTS


async def test_tashkent_city_has_its_twelve_districts(session: AsyncSession) -> None:
    result = await session.execute(
        select(District.name)
        .join(Region, Region.id == District.region_id)
        .where(Region.code == "UZ-TK")
    )
    names = set(result.scalars())

    assert len(names) == 12
    assert {"Chilonzor tumani", "Yunusobod tumani", "Yangihayot tumani"} <= names


async def test_district_coordinates_land_inside_uzbekistan(session: AsyncSession) -> None:
    """A transposed lat/lng puts a district in China; the whole seed is checked at once."""
    result = await session.execute(
        select(District.name, District.latitude, District.longitude).where(
            (District.latitude < MIN_LATITUDE)
            | (District.latitude > MAX_LATITUDE)
            | (District.longitude < MIN_LONGITUDE)
            | (District.longitude > MAX_LONGITUDE)
        )
    )
    assert result.all() == []
