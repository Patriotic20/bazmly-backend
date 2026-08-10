from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.core.dependencies import AdminUser, SessionDep
from app.modules.geo.schemas import DistrictRead, RegionCreate, RegionRead, RegionUpdate
from app.modules.geo.services import LocationService, RegionService

router = APIRouter(prefix="/v1/regions", tags=["geo"])


@router.get(
    "",
    response_model=list[RegionRead],
    operation_id="geo_list_regions",
    summary="Viloyatlar ro'yxati",
    description="Toshkent, Navoiy, Samarqand, Buxoro va boshqalar.",
)
async def list_regions(session: SessionDep) -> Sequence[RegionRead]:
    return await LocationService(session).list_regions()


@router.get(
    "/{region_id}/districts",
    response_model=list[DistrictRead],
    operation_id="geo_list_districts",
    summary="Tumanlar ro'yxati",
    description="Tuman va shahar bir darajada; API da bu `district` deb ataladi.",
)
async def list_districts(
    session: SessionDep, region_id: Annotated[int, Path(ge=1)]
) -> Sequence[DistrictRead]:
    return await LocationService(session).list_districts(region_id)


@router.post(
    "",
    response_model=RegionRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="geo_create_region",
    summary="Viloyat qo'shish",
    description="Faqat administrator uchun.",
)
async def create_region(payload: RegionCreate, session: SessionDep, _: AdminUser) -> RegionRead:
    return await RegionService(session).create(payload)


@router.patch(
    "/{region_id}",
    response_model=RegionRead,
    operation_id="geo_update_region",
    summary="Viloyatni tahrirlash",
    description="Faqat administrator uchun.",
)
async def update_region(
    payload: RegionUpdate,
    session: SessionDep,
    _: AdminUser,
    region_id: Annotated[int, Path(ge=1)],
) -> RegionRead:
    return await RegionService(session).update(region_id, payload)


@router.delete(
    "/{region_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="geo_delete_region",
    summary="Viloyatni o'chirish",
    description="Faqat administrator uchun. Tumanlari bo'lgan viloyatni o'chirib bo'lmaydi.",
)
async def delete_region(
    session: SessionDep, _: AdminUser, region_id: Annotated[int, Path(ge=1)]
) -> None:
    await RegionService(session).delete(region_id)
