from fastapi import APIRouter

from app.core.dependencies import CurrentUser, LanguageId, SessionDep, require_permission
from app.modules.venue_groups.schemas import (
    VenueGroupRead,
    VenueGroupUpdate,
    VenueGroupWithBranchesRead,
)
from app.modules.venue_groups.services import VenueGroupService

router = APIRouter(prefix="/v1/venue/groups", tags=["venue:groups"])


@router.get(
    "/me",
    response_model=VenueGroupRead,
    operation_id="venue_groups_get_mine",
    summary="My chain",
    description="The venue group owned by the signed-in account.",
)
async def get_mine(user: CurrentUser, session: SessionDep) -> VenueGroupRead:
    return await VenueGroupService(session).get_for_owner(user.id)


@router.get(
    "/{group_id}/branches",
    response_model=VenueGroupWithBranchesRead,
    operation_id="venue_groups_get_with_branches",
    summary="Chain with its branches",
    description="The dashboard header name plus every filial under it.",
)
async def get_with_branches(
    user: CurrentUser, language_id: LanguageId, session: SessionDep, group_id: int
) -> VenueGroupWithBranchesRead:
    return await VenueGroupService(session).get_with_branches(group_id, language_id)


@router.patch(
    "/{group_id}",
    response_model=VenueGroupRead,
    operation_id="venue_groups_update",
    summary="Edit the chain",
    description=(
        "Logo and default currency. The logo lives here, never on a filial. "
        "Pass venue_id for the permission check — a group-scoped owner satisfies it "
        "at any branch in the chain."
    ),
    dependencies=[require_permission("settings.edit")],
)
async def update_group(
    payload: VenueGroupUpdate, user: CurrentUser, session: SessionDep, group_id: int
) -> VenueGroupRead:
    return await VenueGroupService(session).update_details(group_id, payload)
