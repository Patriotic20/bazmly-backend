from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.geo.models import District
from app.modules.geo.models.user_recent_location import UserRecentLocation
from app.modules.venues.models import Venue


class DistrictRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, district_id: int) -> District | None:
        result = await self.session.execute(select(District).where(District.id == district_id))
        return result.scalar_one_or_none()

    async def list_by_region(self, region_id: int) -> Sequence[District]:
        result = await self.session.execute(
            select(District).where(District.region_id == region_id).order_by(District.name)
        )
        return result.scalars().all()

    async def count_for_region(self, region_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(District).where(District.region_id == region_id)
        )
        return result.scalar_one()

    async def create(
        self, region_id: int, name: str, latitude: Decimal, longitude: Decimal
    ) -> District:
        district = District(region_id=region_id, name=name, latitude=latitude, longitude=longitude)
        self.session.add(district)
        await self.session.flush()
        return district

    async def update_fields(self, district_id: int, values: dict[str, Any]) -> District | None:
        """Partial update from an already-validated `DistrictUpdate`.

        Empty `values` is a no-op returning the row, so a caller that filtered
        everything out does not issue an `UPDATE ... SET` with nothing to set.
        """
        if not values:
            return await self.get_by_id(district_id)
        result = await self.session.execute(
            update(District).where(District.id == district_id).values(**values).returning(District)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def delete(self, district: District) -> None:
        await self.session.delete(district)
        await self.session.flush()

    async def count_references(self, district_id: int) -> int:
        """Rows in `venues` and `user_recent_locations` pinned to this district.

        Both tables carry a `district_id` FK; a raw delete that only checked one
        would leave the other to fail as a 500 instead of a clean refusal.
        """
        venue_count = await self.session.execute(
            select(func.count()).select_from(Venue).where(Venue.district_id == district_id)
        )
        recent_location_count = await self.session.execute(
            select(func.count())
            .select_from(UserRecentLocation)
            .where(UserRecentLocation.district_id == district_id)
        )
        return venue_count.scalar_one() + recent_location_count.scalar_one()
