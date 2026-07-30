from collections.abc import Sequence
from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.core.dependencies import (
    ClientLocationDep,
    LanguageId,
    OptionalUser,
    PaginationDep,
    SessionDep,
)
from app.core.pagination import Page
from app.modules.bookings.schemas import AvailableTableRead, BlockedDatesRead
from app.modules.bookings.services import AvailabilityService
from app.modules.menu.schemas import MenuItemListItem
from app.modules.menu.services import MenuService
from app.modules.reviews.schemas import ReviewListItem
from app.modules.reviews.services import ReviewService
from app.modules.services.schemas import VenueServiceRead
from app.modules.services.services import VenueServiceCatalogService
from app.modules.venues.api.dependencies import VenueServiceDep, VenueTableServiceDep
from app.modules.venues.schemas import (
    VenueDetailRead,
    VenueListItem,
    VenueSearchParams,
    VenueZoneRead,
)

router = APIRouter(prefix="/v1/venues", tags=["venues"])


@router.get(
    "/search",
    response_model=Page[VenueListItem],
    operation_id="venues_search",
    summary="Search venues",
    description="The home screen. Returns distance_m and is_open_now per card.",
)
async def search(
    params: Annotated[VenueSearchParams, Query()],
    location: ClientLocationDep,
    language_id: LanguageId,
    user: OptionalUser,
    service: VenueServiceDep,
) -> Page[VenueListItem]:
    return await service.search(_with_location(params, location), language_id)


def _with_location(params: VenueSearchParams, location: ClientLocationDep) -> VenueSearchParams:
    """Coordinates arrive as `lat`/`lng` query params, validated as a pair."""
    if location is None:
        return params
    return params.model_copy(
        update={"latitude": location.latitude, "longitude": location.longitude}
    )


@router.get(
    "/{venue_id}",
    response_model=VenueDetailRead,
    operation_id="venues_get_detail",
    summary="Venue detail",
    description="Photos, amenities, types and working hours, plus is_open_now.",
)
async def get_detail(
    language_id: LanguageId,
    user: OptionalUser,
    service: VenueServiceDep,
    venue_id: Annotated[int, Path(ge=1)],
) -> VenueDetailRead:
    return await service.get_detail(venue_id, language_id)


@router.get(
    "/{venue_id}/availability",
    response_model=BlockedDatesRead,
    operation_id="venues_get_availability",
    summary="Dates already taken",
    description="Greyed-out chips in the date picker: days a hall event already owns.",
)
async def get_availability(
    session: SessionDep,
    venue_id: Annotated[int, Path(ge=1)],
    date_from: Annotated[date, Query()],
    date_to: Annotated[date, Query()],
) -> BlockedDatesRead:
    return await AvailabilityService(session).blocked_dates(venue_id, date_from, date_to)


@router.get(
    "/{venue_id}/tables",
    response_model=list[AvailableTableRead],
    operation_id="venues_list_free_tables",
    summary="Free tables for a window",
    description="Excludes tables with an overlapping booking or a blocked slot.",
)
async def list_free_tables(
    session: SessionDep,
    venue_id: Annotated[int, Path(ge=1)],
    booking_date: Annotated[date, Query()],
    start_time: Annotated[time, Query()],
    end_time: Annotated[time, Query()],
    min_seats: Annotated[int, Query(ge=1)] = 1,
) -> Sequence[AvailableTableRead]:
    return await AvailabilityService(session).available_tables(
        venue_id, booking_date, start_time, end_time, min_seats
    )


@router.get(
    "/{venue_id}/zones",
    response_model=list[VenueZoneRead],
    operation_id="venues_list_zones",
    summary="List seating zones",
    description="Ichkari, Tashqari. Umumiy is a client-side no-filter, never a row.",
)
async def list_zones(
    language_id: LanguageId,
    service: VenueTableServiceDep,
    venue_id: Annotated[int, Path(ge=1)],
) -> Sequence[VenueZoneRead]:
    return await service.list_zones(venue_id, language_id)


@router.get(
    "/{venue_id}/menu",
    response_model=list[MenuItemListItem],
    operation_id="venues_list_menu_items",
    summary="Menu for a branch",
    description="Only dishes this filial serves, priced with its branch override.",
)
async def list_menu_items(
    session: SessionDep,
    language_id: LanguageId,
    venue_id: Annotated[int, Path(ge=1)],
    category_id: Annotated[int | None, Query(ge=1)] = None,
) -> Sequence[MenuItemListItem]:
    return await MenuService(session).list_items(venue_id, language_id, category_id)


@router.get(
    "/{venue_id}/services",
    response_model=list[VenueServiceRead],
    operation_id="venues_list_services",
    summary="Additional services",
    description="Qo'shimcha xizmatlar: dasturxon tuzash, raqqoslar, kartej and the rest.",
)
async def list_services(
    session: SessionDep,
    language_id: LanguageId,
    venue_id: Annotated[int, Path(ge=1)],
    group_id: Annotated[int, Query(ge=1)],
) -> Sequence[VenueServiceRead]:
    return await VenueServiceCatalogService(session).list_for_venue(venue_id, group_id, language_id)


@router.get(
    "/{venue_id}/reviews",
    response_model=Page[ReviewListItem],
    operation_id="venues_list_reviews",
    summary="Published reviews",
    description="Verified reviews are those attached to a completed booking.",
)
async def list_reviews(
    session: SessionDep,
    pagination: PaginationDep,
    venue_id: Annotated[int, Path(ge=1)],
) -> Page[ReviewListItem]:
    return await ReviewService(session).list_for_venue(
        venue_id, pagination.limit, pagination.offset
    )
