from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.geo.repositories import (
    DistrictRepository,
    RegionRepository,
    UserRecentLocationRepository,
)
from app.modules.geo.schemas import (
    DistrictRead,
    RegionRead,
    RegionWithDistrictsRead,
    UserAddressCreate,
    UserAddressRead,
)

RECENT_CAP = 10


class LocationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.regions = RegionRepository(session)
        self.districts = DistrictRepository(session)
        self.recent = UserRecentLocationRepository(session)

    async def list_regions(self) -> Sequence[RegionRead]:
        return [RegionRead.model_validate(row) for row in await self.regions.list_all()]

    async def list_districts(self, region_id: int) -> Sequence[DistrictRead]:
        return [
            DistrictRead.model_validate(row)
            for row in await self.districts.list_by_region(region_id)
        ]

    async def get_region_with_districts(self, region_id: int) -> RegionWithDistrictsRead:
        result = await self.regions.get_with_districts(region_id)
        if result is None:
            raise NotFoundError("Viloyat topilmadi")
        return RegionWithDistrictsRead(
            id=result.region.id,
            name=result.region.name,
            code=result.region.code,
            districts=[DistrictRead.model_validate(row) for row in result.districts],
        )

    async def list_recent(self, user_id: int) -> Sequence[UserAddressRead]:
        rows = await self.recent.list_for_user(user_id, RECENT_CAP)
        return [UserAddressRead.model_validate(row) for row in rows]

    async def remember(self, user_id: int, payload: UserAddressCreate) -> UserAddressRead:
        """Upsert then trim, in one unit of work.

        Trimming inside the same transaction is what keeps "Oxirgi manzillar" at
        ten rows; doing it later would let a burst of picks grow the list unbounded
        between runs.
        """
        district = await self.districts.get_by_id(payload.district_id)
        if district is None:
            raise NotFoundError("Tuman topilmadi")

        location = await self.recent.upsert(
            user_id=user_id,
            district_id=payload.district_id,
            label=payload.label,
            latitude=payload.latitude,
            longitude=payload.longitude,
        )
        await self.recent.trim_to_limit(user_id, RECENT_CAP)
        await self.session.commit()
        return UserAddressRead.model_validate(location)
