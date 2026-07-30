from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.dependencies import CurrentUser, LanguageId, SessionDep, require_permission
from app.modules.services.schemas import (
    ServiceCatalogRead,
    VenueServiceCreate,
    VenueServiceRead,
)
from app.modules.services.services import VenueServiceCatalogService

router = APIRouter(prefix="/v1", tags=["services"])


@router.get(
    "/service-catalog",
    response_model=list[ServiceCatalogRead],
    operation_id="services_list_catalog",
    summary="Xizmatlar katalogi",
    description="Qo'shimcha xizmatlar — platforma tomonidan belgilangan yopiq ro'yxat.",
)
async def list_catalog(
    session: SessionDep,
    language_id: LanguageId,
    venue_type_id: Annotated[int | None, Query(ge=1)] = None,
) -> Sequence[ServiceCatalogRead]:
    return await VenueServiceCatalogService(session).list_catalog(language_id, venue_type_id)


@router.post(
    "/venue/services",
    response_model=VenueServiceRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="venue_services_create",
    summary="Xizmatga narx belgilash",
    description="Filial narxi shu xizmat uchun tarmoq narxidan ustun turadi.",
    dependencies=[require_permission("settings.edit")],
)
async def create_venue_service(
    payload: VenueServiceCreate,
    user: CurrentUser,
    session: SessionDep,
    venue_id: Annotated[int, Query(ge=1)],
    group_id: Annotated[int, Query(ge=1)],
) -> VenueServiceRead:
    return await VenueServiceCatalogService(session).create(user.id, venue_id, group_id, payload)
