from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.modules.geo.repositories import DistrictRepository, RegionRepository
from app.modules.geo.schemas import DistrictCreate, DistrictRead, DistrictUpdate


class DistrictService:
    """Admin writes over `districts`. Reads stay in `LocationService`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.districts = DistrictRepository(session)
        self.regions = RegionRepository(session)

    async def create(self, payload: DistrictCreate) -> DistrictRead:
        if await self.regions.get_by_id(payload.region_id) is None:
            raise NotFoundError("Viloyat topilmadi")
        district = await self.districts.create(
            region_id=payload.region_id,
            name=payload.name,
            latitude=payload.latitude,
            longitude=payload.longitude,
        )
        await self.session.commit()
        return DistrictRead.model_validate(district)

    async def update(self, district_id: int, payload: DistrictUpdate) -> DistrictRead:
        district = await self.districts.get_by_id(district_id)
        if district is None:
            raise NotFoundError("Tuman topilmadi")

        changes = payload.model_dump(exclude_unset=True)
        new_region_id = changes.get("region_id")
        if new_region_id is not None and await self.regions.get_by_id(new_region_id) is None:
            raise NotFoundError("Viloyat topilmadi")

        updated = await self.districts.update_fields(district_id, changes)
        if updated is None:
            raise NotFoundError("Tuman topilmadi")

        await self.session.commit()
        return DistrictRead.model_validate(updated)

    async def delete(self, district_id: int) -> None:
        district = await self.districts.get_by_id(district_id)
        if district is None:
            raise NotFoundError("Tuman topilmadi")
        if await self.districts.count_references(district_id) > 0:
            raise ValidationFailedError(
                "Bu tuman ishlatilmoqda, uni o'chirish mumkin emas",
                details={"district_id": district_id},
            )
        await self.districts.delete(district)
        await self.session.commit()
