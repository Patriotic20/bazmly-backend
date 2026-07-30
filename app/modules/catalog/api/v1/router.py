from collections.abc import Sequence

from fastapi import APIRouter

from app.core.dependencies import LanguageId, SessionDep
from app.modules.catalog.schemas import AmenityRead, VenueTypeRead
from app.modules.catalog.services import CatalogService

router = APIRouter(prefix="/v1", tags=["catalog"])


@router.get(
    "/venue-types",
    response_model=list[VenueTypeRead],
    operation_id="catalog_list_venue_types",
    summary="List venue types",
    description="Restoran, To'yxona, Kafe. Barchasi is a client-side shortcut, never a row.",
)
async def list_venue_types(session: SessionDep, language_id: LanguageId) -> Sequence[VenueTypeRead]:
    return await CatalogService(session).list_venue_types(language_id)


@router.get(
    "/amenities",
    response_model=list[AmenityRead],
    operation_id="catalog_list_amenities",
    summary="List amenities",
    description="Parking, sound system, stage, air conditioning, kitchen, Wi-Fi.",
)
async def list_amenities(session: SessionDep, language_id: LanguageId) -> Sequence[AmenityRead]:
    return await CatalogService(session).list_amenities(language_id)
