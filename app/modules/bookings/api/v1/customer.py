from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.core.dependencies import CurrentUser, LanguageId
from app.modules.bookings.api.dependencies import BookingServiceDep
from app.modules.bookings.enums import BookingStatus
from app.modules.bookings.schemas import (
    BookingCancel,
    BookingListItem,
    BookingOwnerDetail,
    BookingRead,
    HallEventCreate,
    TableReservationCreate,
)

router = APIRouter(prefix="/v1/bookings", tags=["bookings"])


@router.post(
    "/table",
    response_model=BookingOwnerDetail,
    status_code=status.HTTP_201_CREATED,
    operation_id="bookings_create_table_reservation",
    summary="Book a table",
    description="Restaurant reservation. Double booking returns 409 table_already_booked.",
)
async def create_table_reservation(
    payload: TableReservationCreate,
    user: CurrentUser,
    language_id: LanguageId,
    service: BookingServiceDep,
) -> BookingOwnerDetail:
    return await service.create_table_reservation(user.id, payload, language_id)


@router.post(
    "/hall",
    response_model=BookingOwnerDetail,
    status_code=status.HTTP_201_CREATED,
    operation_id="bookings_create_hall_event",
    summary="Book a hall",
    description="To'yxona event. The guest tier is resolved from the party size.",
)
async def create_hall_event(
    payload: HallEventCreate,
    user: CurrentUser,
    language_id: LanguageId,
    service: BookingServiceDep,
) -> BookingOwnerDetail:
    return await service.create_hall_event(user.id, payload, language_id)


@router.get(
    "",
    response_model=list[BookingListItem],
    operation_id="bookings_list_mine",
    summary="My bookings",
    description="The Joylar tab. Carries no qr_token — a list is too easy to screenshot.",
)
async def list_mine(
    user: CurrentUser,
    language_id: LanguageId,
    service: BookingServiceDep,
    statuses: Annotated[list[BookingStatus] | None, Query()] = None,
) -> Sequence[BookingListItem]:
    return await service.list_for_user(user.id, language_id, statuses)


@router.get(
    "/{booking_id}",
    response_model=BookingOwnerDetail,
    operation_id="bookings_get_detail",
    summary="Booking detail",
    description="The owner's own booking, including its single-use qr_token.",
)
async def get_detail(
    user: CurrentUser,
    service: BookingServiceDep,
    booking_id: Annotated[int, Path(ge=1)],
) -> BookingOwnerDetail:
    return await service.get_detail(user.id, booking_id)


@router.post(
    "/{booking_id}/cancel",
    response_model=BookingRead,
    operation_id="bookings_cancel",
    summary="Cancel a booking",
    description="Inside the deposit window the deposit is forfeited; the reason is recorded.",
)
async def cancel(
    payload: BookingCancel,
    user: CurrentUser,
    service: BookingServiceDep,
    booking_id: Annotated[int, Path(ge=1)],
) -> BookingRead:
    return await service.cancel(user.id, booking_id, payload)
