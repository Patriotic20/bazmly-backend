from typing import Annotated

from fastapi import Depends

from app.core.dependencies import SessionDep
from app.modules.bookings.services import AvailabilityService, BookingService


def get_booking_service(session: SessionDep) -> BookingService:
    return BookingService(session)


def get_availability_service(session: SessionDep) -> AvailabilityService:
    return AvailabilityService(session)


BookingServiceDep = Annotated[BookingService, Depends(get_booking_service)]
AvailabilityServiceDep = Annotated[AvailabilityService, Depends(get_availability_service)]
