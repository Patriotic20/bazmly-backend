from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.geo.models import District, Region


@dataclass(frozen=True, slots=True)
class RegionWithDistricts:
    """A viloyat and its tuman/shahar rows, both fetched explicitly."""

    region: Region
    districts: Sequence[District]


class RegionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, region_id: int) -> Region | None:
        result = await self.session.execute(select(Region).where(Region.id == region_id))
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[Region]:
        result = await self.session.execute(select(Region).order_by(Region.name))
        return result.scalars().all()

    async def get_with_districts(self, region_id: int) -> RegionWithDistricts | None:
        region = await self.get_by_id(region_id)
        if region is None:
            return None
        result = await self.session.execute(
            select(District).where(District.region_id == region_id).order_by(District.name)
        )
        return RegionWithDistricts(region=region, districts=result.scalars().all())
