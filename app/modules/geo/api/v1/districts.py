from typing import Annotated

from fastapi import APIRouter, Path, status

from app.core.dependencies import AdminUser, SessionDep
from app.modules.geo.schemas import DistrictCreate, DistrictRead, DistrictUpdate
from app.modules.geo.services import DistrictService

router = APIRouter(prefix="/v1/districts", tags=["geo"])


@router.post(
    "",
    response_model=DistrictRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="geo_create_district",
    summary="Tuman qo'shish",
    description="Faqat administrator uchun.",
)
async def create_district(
    payload: DistrictCreate, session: SessionDep, _: AdminUser
) -> DistrictRead:
    return await DistrictService(session).create(payload)


@router.patch(
    "/{district_id}",
    response_model=DistrictRead,
    operation_id="geo_update_district",
    summary="Tumanni tahrirlash",
    description="Faqat administrator uchun.",
)
async def update_district(
    payload: DistrictUpdate,
    session: SessionDep,
    _: AdminUser,
    district_id: Annotated[int, Path(ge=1)],
) -> DistrictRead:
    return await DistrictService(session).update(district_id, payload)


@router.delete(
    "/{district_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="geo_delete_district",
    summary="Tumanni o'chirish",
    description=(
        "Faqat administrator uchun. Muassasalari yoki so'nggi manzillari bo'lgan "
        "tumanni o'chirib bo'lmaydi."
    ),
)
async def delete_district(
    session: SessionDep, _: AdminUser, district_id: Annotated[int, Path(ge=1)]
) -> None:
    await DistrictService(session).delete(district_id)
