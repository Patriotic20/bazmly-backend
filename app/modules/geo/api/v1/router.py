from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Path

from app.core.dependencies import SessionDep
from app.modules.geo.schemas import DistrictRead, RegionRead
from app.modules.geo.services import LocationService

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
