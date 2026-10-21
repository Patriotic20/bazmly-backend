from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.dependencies import SessionDep, require_permission
from app.modules.auth.schemas import UserRead
from app.modules.services.schemas import (
    ServiceCatalogRead,
    VenueServiceCreate,
    VenueServiceRead,
)
from app.modules.services.services import VenueServiceCatalogService
from app.modules.venues.enums import VenueTypeSlug

# Two routers, one file: the catalog is read by both apps, but setting a price
# is staff work. Separate tags — not one router with per-operation overrides,
# which FastAPI would merge into a double-tagged operation shown twice in Swagger.
catalog_router = APIRouter(prefix="/v1", tags=["services"])
venue_router = APIRouter(prefix="/v1", tags=["venue:services"])


@catalog_router.get(
    "/service-catalog",
    response_model=list[ServiceCatalogRead],
    operation_id="services_list_catalog",
    summary="Xizmatlar katalogi",
    description="Qo'shimcha xizmatlar — platforma tomonidan belgilangan yopiq ro'yxat.",
)
async def list_catalog(
    session: SessionDep,
    venue_type: Annotated[VenueTypeSlug | None, Query()] = None,
) -> Sequence[ServiceCatalogRead]:
    return await VenueServiceCatalogService(session).list_catalog(venue_type)


@venue_router.post(
    "/venue/services",
    response_model=VenueServiceRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="venue_services_create",
    summary="Xizmatga narx belgilash",
    description="Filial narxi shu xizmat uchun tarmoq narxidan ustun turadi.",
)
async def create_venue_service(
    payload: VenueServiceCreate,
    user: Annotated[UserRead, require_permission("settings.edit")],
    session: SessionDep,
    venue_id: Annotated[int, Query(ge=1)],
    group_id: Annotated[int, Query(ge=1)],
) -> VenueServiceRead:
    return await VenueServiceCatalogService(session).create(user.id, venue_id, group_id, payload)


router = APIRouter()
router.include_router(catalog_router)
router.include_router(venue_router)
