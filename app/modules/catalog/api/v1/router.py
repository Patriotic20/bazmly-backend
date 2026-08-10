from collections.abc import Sequence

from fastapi import APIRouter

from app.core.dependencies import SessionDep
from app.modules.catalog.schemas import AmenityRead, VenueTypeRead
from app.modules.catalog.services import CatalogService

router = APIRouter(prefix="/v1", tags=["catalog"])


@router.get(
    "/venue-types",
    response_model=list[VenueTypeRead],
    operation_id="catalog_list_venue_types",
    summary="Muassasa turlari",
    description="Restoran, To'yxona, Kafe. Barchasi — bu filtrsiz ko'rinish, alohida tur emas.",
)
async def list_venue_types(session: SessionDep) -> Sequence[VenueTypeRead]:
    return await CatalogService(session).list_venue_types()


@router.get(
    "/amenities",
    response_model=list[AmenityRead],
    operation_id="catalog_list_amenities",
    summary="Qulayliklar ro'yxati",
    description="Parkovka, ovoz tizimi, sahna, konditsioner, professional oshxona, Wi-Fi.",
)
async def list_amenities(session: SessionDep) -> Sequence[AmenityRead]:
    return await CatalogService(session).list_amenities()
