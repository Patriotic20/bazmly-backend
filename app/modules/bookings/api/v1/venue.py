"""Staff-facing booking routes — Kutilayotgan mijozlar."""

from collections.abc import Sequence
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.core.dependencies import CurrentUser, require_permission
from app.modules.auth.schemas import UserRead
from app.modules.bookings.api.dependencies import AvailabilityServiceDep, BookingServiceDep
from app.modules.bookings.enums import BookingStatus
from app.modules.bookings.schemas import (
    BlockedDatesRead,
    BookingRead,
    CheckInRequest,
    SeatedSummary,
)

router = APIRouter(prefix="/v1/venue/bookings", tags=["venue:bookings"])


@router.get(
    "",
    response_model=list[BookingRead],
    operation_id="venue_bookings_list_day",
    summary="Kutilayotgan mijozlar",
    description="Bitta filialning bitta kundagi bronlari.",
)
async def list_day(
    user: CurrentUser,
    service: BookingServiceDep,
    venue_id: Annotated[int, Query(ge=1)],
    day: Annotated[date, Query()],
    statuses: Annotated[list[BookingStatus] | None, Query()] = None,
) -> Sequence[BookingRead]:
    return await service.venue_day(venue_id, day, statuses)


@router.post(
    "/check-in",
    response_model=BookingRead,
    operation_id="venue_bookings_check_in",
    summary="QR orqali qayd etish",
    description=(
        "Bir marta ishlatiladi: ikkinchi skan rad etiladi. Skanerlovchi shu "
        "filialda ishlashi shart."
    ),
)
async def check_in(
    payload: CheckInRequest,
    service: BookingServiceDep,
    user: Annotated[UserRead, require_permission("bookings.confirm")],
) -> BookingRead:
    return await service.check_in_by_qr(user.id, payload.venue_id, payload.qr_token)


@router.post(
    "/{booking_id}/check-out",
    response_model=SeatedSummary,
    operation_id="venue_bookings_check_out",
    summary="Tashrifni yakunlash",
    description="`seated_minutes` haqiqiy vaqt oralig'idan bir marta yoziladi.",
)
async def check_out(
    user: Annotated[UserRead, require_permission("bookings.confirm")],
    service: BookingServiceDep,
    booking_id: Annotated[int, Path(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
) -> SeatedSummary:
    return await service.check_out(user.id, venue_id, booking_id)


@router.get(
    "/blocked-dates",
    response_model=BlockedDatesRead,
    operation_id="venue_bookings_blocked_dates",
    summary="Band kunlar",
    description="Shu filialda to'yxona tadbiri egallagan kunlar.",
)
async def blocked_dates(
    user: CurrentUser,
    service: AvailabilityServiceDep,
    venue_id: Annotated[int, Query(ge=1)],
    date_from: Annotated[date, Query()],
    date_to: Annotated[date, Query()],
) -> BlockedDatesRead:
    return await service.blocked_dates(venue_id, date_from, date_to)
