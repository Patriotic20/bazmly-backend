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
    summary="Mening tarmog'im",
    description="Kirgan akkauntga tegishli tarmoq.",
)
async def get_mine(user: CurrentUser, session: SessionDep) -> VenueGroupRead:
    return await VenueGroupService(session).get_for_owner(user.id)


@router.get(
    "/{group_id}/branches",
    response_model=VenueGroupWithBranchesRead,
    operation_id="venue_groups_get_with_branches",
    summary="Tarmoq va filiallari",
    description="Boshqaruv panelidagi tarmoq nomi va uning barcha filiallari.",
)
async def get_with_branches(
    user: CurrentUser, language_id: LanguageId, session: SessionDep, group_id: int
) -> VenueGroupWithBranchesRead:
    return await VenueGroupService(session).get_with_branches(group_id, language_id)


@router.patch(
    "/{group_id}",
    response_model=VenueGroupRead,
    operation_id="venue_groups_update",
    summary="Tarmoqni tahrirlash",
    description=(
        "Logotip va asosiy valyuta. Logotip aynan shu yerda saqlanadi, filialda "
        "emas. Ruxsatni tekshirish uchun `venue_id` yuboriladi — tarmoq darajasidagi "
        "egasi tarmoqning istalgan filiali uchun bu tekshiruvdan o'tadi."
    ),
    dependencies=[require_permission("settings.edit")],
)
async def update_group(
    payload: VenueGroupUpdate, user: CurrentUser, session: SessionDep, group_id: int
) -> VenueGroupRead:
    return await VenueGroupService(session).update_details(group_id, payload)
