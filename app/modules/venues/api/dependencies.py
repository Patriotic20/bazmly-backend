from typing import Annotated

from fastapi import Depends

from app.core.dependencies import SessionDep
from app.modules.venues.services import (
    VenueOnboardingService,
    VenueService,
    VenueTableService,
)


def get_venue_service(session: SessionDep) -> VenueService:
    return VenueService(session)


def get_venue_table_service(session: SessionDep) -> VenueTableService:
    return VenueTableService(session)


def get_onboarding_service(session: SessionDep) -> VenueOnboardingService:
    return VenueOnboardingService(session)


VenueServiceDep = Annotated[VenueService, Depends(get_venue_service)]
VenueTableServiceDep = Annotated[VenueTableService, Depends(get_venue_table_service)]
OnboardingServiceDep = Annotated[VenueOnboardingService, Depends(get_onboarding_service)]
