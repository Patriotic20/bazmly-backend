"""Staff-facing venue routes — Filiallar.

Separate from `customer.py` on purpose: an owner listing their branches and a
guest searching venues want different payloads and different filters. Branching on
role inside one endpoint would make the response shape depend on the caller, which
no generated client can express.
"""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.core.dependencies import CurrentUser, LanguageId, require_permission
from app.modules.venues.api.dependencies import (
    OnboardingServiceDep,
    VenueServiceDep,
    VenueTableServiceDep,
)
from app.modules.venues.schemas import (
    TableCountsCreate,
    VenueRead,
    VenueStatusCountsRead,
    VenueTableRead,
    VenueUpdate,
    VenueZoneRead,
    WorkingHoursReplace,
)

router = APIRouter(prefix="/v1/venue/venues", tags=["venue:venues"])


@router.get(
    "",
    response_model=list[VenueRead],
    operation_id="venue_venues_list",
    summary="List branches",
    description="Filiallar for the signed-in owner's chain.",
)
async def list_branches(
    user: CurrentUser,
    service: VenueServiceDep,
    group_id: Annotated[int, Query(ge=1)],
    status: Annotated[str | None, Query()] = None,
) -> Sequence[VenueRead]:
    return await service.list_for_group(group_id, status)


@router.get(
    "/counts",
    response_model=VenueStatusCountsRead,
    operation_id="venue_venues_status_counts",
    summary="Branch counters",
    description="Jami / Aktiv / Yopiq on the Filiallar header, in one grouped query.",
)
async def status_counts(
    user: CurrentUser,
    service: VenueServiceDep,
    group_id: Annotated[int, Query(ge=1)],
) -> VenueStatusCountsRead:
    return await service.status_counts(group_id)


@router.get(
    "/{venue_id}",
    response_model=VenueRead,
    operation_id="venue_venues_get",
    summary="Get one branch",
    description="The owner-side view of a filial.",
)
async def get_branch(
    language_id: LanguageId,
    service: VenueServiceDep,
    venue_id: Annotated[int, Path(ge=1)],
    user: CurrentUser,
) -> VenueRead:
    detail = await service.get_detail(venue_id, language_id)
    return detail.venue


@router.patch(
    "/{venue_id}",
    response_model=VenueRead,
    operation_id="venue_venues_update",
    summary="Edit a branch",
    description="Address, capacity, deposit policy and booking lead time.",
    dependencies=[require_permission("branch.manage")],
)
async def update_branch(
    payload: VenueUpdate,
    user: CurrentUser,
    service: VenueServiceDep,
    venue_id: Annotated[int, Path(ge=1)],
) -> VenueRead:
    return await service.update_details(user.id, venue_id, payload)


@router.put(
    "/{venue_id}/working-hours",
    response_model=VenueRead,
    operation_id="venue_venues_replace_working_hours",
    summary="Replace the working week",
    description="Rewrites all seven rows, so a removed day cannot survive as a stale row.",
    dependencies=[require_permission("branch.manage")],
)
async def replace_working_hours(
    payload: WorkingHoursReplace,
    service: OnboardingServiceDep,
    venue_id: Annotated[int, Path(ge=1)],
    total_seats: Annotated[int | None, Query(ge=1)] = None,
) -> VenueRead:
    return await service.set_hours_and_seats(venue_id, payload, total_seats)


@router.get(
    "/{venue_id}/tables",
    response_model=list[VenueTableRead],
    operation_id="venue_venues_list_tables",
    summary="List tables",
    description="Numbered stollar for the Buyurtmalar board.",
)
async def list_tables(
    user: CurrentUser,
    service: VenueTableServiceDep,
    venue_id: Annotated[int, Path(ge=1)],
    zone_id: Annotated[int | None, Query(ge=1)] = None,
) -> Sequence[VenueTableRead]:
    return await service.list_for_venue(venue_id, zone_id)


@router.post(
    "/{venue_id}/tables/bulk",
    response_model=list[VenueTableRead],
    status_code=201,
    operation_id="venue_venues_create_tables_bulk",
    summary="Create tables from capacity counts",
    description="Onboarding's 2/4/6/8/10+ buckets, expanded into numbered rows.",
    dependencies=[require_permission("branch.manage")],
)
async def create_tables_bulk(
    payload: TableCountsCreate,
    user: CurrentUser,
    service: VenueTableServiceDep,
    venue_id: Annotated[int, Path(ge=1)],
) -> Sequence[VenueTableRead]:
    return await service.create_from_counts(user.id, venue_id, payload)


@router.get(
    "/{venue_id}/zones",
    response_model=list[VenueZoneRead],
    operation_id="venue_venues_list_zones",
    summary="List zones",
    description="Ichkari and Tashqari, used by the Stollar board's filter chips.",
)
async def list_zones(
    user: CurrentUser,
    language_id: LanguageId,
    service: VenueTableServiceDep,
    venue_id: Annotated[int, Path(ge=1)],
) -> Sequence[VenueZoneRead]:
    return await service.list_zones(venue_id, language_id)


@router.patch(
    "/{venue_id}/onboarding/address",
    response_model=VenueRead,
    operation_id="venue_venues_onboarding_address",
    summary="Onboarding: address",
    description="Advances onboarding_step so a half-finished wizard can resume.",
    dependencies=[require_permission("branch.manage")],
)
async def onboarding_address(
    payload: VenueUpdate,
    service: OnboardingServiceDep,
    venue_id: Annotated[int, Path(ge=1)],
) -> VenueRead:
    return await service.set_address(venue_id, payload)


@router.patch(
    "/{venue_id}/onboarding/tables-done",
    response_model=VenueRead,
    operation_id="venue_venues_onboarding_tables_done",
    summary="Onboarding: tables complete",
    description="Marks the Stollar step finished.",
    dependencies=[require_permission("branch.manage")],
)
async def onboarding_tables_done(
    service: OnboardingServiceDep, venue_id: Annotated[int, Path(ge=1)]
) -> VenueRead:
    return await service.mark_tables_done(venue_id)


@router.patch(
    "/{venue_id}/onboarding/services-done",
    response_model=VenueRead,
    operation_id="venue_venues_onboarding_services_done",
    summary="Onboarding: services complete",
    description="Marks the Qo'shimcha xizmatlar step finished.",
    dependencies=[require_permission("branch.manage")],
)
async def onboarding_services_done(
    service: OnboardingServiceDep, venue_id: Annotated[int, Path(ge=1)]
) -> VenueRead:
    return await service.mark_services_done(venue_id)


@router.patch(
    "/{venue_id}/onboarding/media-done",
    response_model=VenueRead,
    operation_id="venue_venues_onboarding_media_done",
    summary="Onboarding: media complete",
    description="Marks the Media va vizual step finished.",
    dependencies=[require_permission("branch.manage")],
)
async def onboarding_media_done(
    service: OnboardingServiceDep, venue_id: Annotated[int, Path(ge=1)]
) -> VenueRead:
    return await service.mark_media_done(venue_id)


@router.post(
    "/{venue_id}/onboarding/finish",
    response_model=VenueRead,
    operation_id="venue_venues_onboarding_finish",
    summary="Go live",
    description="Restaurant is live: sets status active and onboarded_at.",
    dependencies=[require_permission("branch.manage")],
)
async def onboarding_finish(
    service: OnboardingServiceDep, venue_id: Annotated[int, Path(ge=1)]
) -> VenueRead:
    return await service.finish(venue_id)
