from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.core.dependencies import AdminUser, SessionDep
from app.modules.geo.schemas import (
    DistrictCreate,
    DistrictRead,
    DistrictUpdate,
    NearestDistrictRead,
)
from app.modules.geo.services import DistrictService, LocationService

router = APIRouter(prefix="/v1/districts", tags=["geo"])


@router.get(
    "/nearest",
    response_model=NearestDistrictRead,
    operation_id="geo_nearest_district",
    summary="Koordinata bo'yicha eng yaqin tuman",
    description=(
        "Telefon bergan koordinatadan tuman va viloyatni aniqlaydi — mijoz "
        "o'zining tumanini qo'lda tanlamasligi uchun. Ochiq: manzil hisobdan "
        "oldin ham kerak. `distance_m` — tuman markazigacha bo'lgan masofa."
    ),
)
async def nearest_district(
    session: SessionDep,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
) -> NearestDistrictRead:
    """Public on purpose: a customer picks a location before an account exists.

    Global bounds rather than Uzbekistan's, so a phone reporting a coordinate
    from anywhere still gets an answer with an honest `distance_m` instead of a
    422 the app would have to explain.
    """
    return await LocationService(session).find_nearest_district(lat, lng)


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
