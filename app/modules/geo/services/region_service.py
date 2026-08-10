from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.modules.geo.repositories import DistrictRepository, RegionRepository
from app.modules.geo.schemas import RegionCreate, RegionRead, RegionUpdate


class RegionService:
    """Admin writes over `regions`. Reads stay in `LocationService`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.regions = RegionRepository(session)
        self.districts = DistrictRepository(session)

    async def create(self, payload: RegionCreate) -> RegionRead:
        if await self.regions.get_by_code(payload.code) is not None:
            raise ValidationFailedError("Bu kod allaqachon band", details={"code": payload.code})
        region = await self.regions.create(name=payload.name, code=payload.code)
        await self.session.commit()
        return RegionRead.model_validate(region)

    async def update(self, region_id: int, payload: RegionUpdate) -> RegionRead:
        region = await self.regions.get_by_id(region_id)
        if region is None:
            raise NotFoundError("Viloyat topilmadi")

        changes = payload.model_dump(exclude_unset=True)
        new_code = changes.get("code")
        code_taken = (
            new_code is not None
            and new_code != region.code
            and await self.regions.get_by_code(new_code) is not None
        )
        if code_taken:
            raise ValidationFailedError("Bu kod allaqachon band", details={"code": new_code})

        updated = await self.regions.update_fields(region_id, changes)
        if updated is None:
            raise NotFoundError("Viloyat topilmadi")

        await self.session.commit()
        return RegionRead.model_validate(updated)

    async def delete(self, region_id: int) -> None:
        region = await self.regions.get_by_id(region_id)
        if region is None:
            raise NotFoundError("Viloyat topilmadi")
        if await self.districts.count_for_region(region_id) > 0:
            raise ValidationFailedError(
                "Viloyatni o'chirish uchun avval uning tumanlarini o'chiring",
                details={"region_id": region_id},
            )
        await self.regions.delete(region)
        await self.session.commit()
