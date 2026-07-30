from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.geo.models import District


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
