"""Hodimlar — staff only."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.core.dependencies import CurrentUser, LanguageId, require_permission
from app.modules.staff.api.dependencies import StaffServiceDep
from app.modules.staff.schemas import (
    InvitationAccept,
    StaffCountsRead,
    StaffInvitationCreate,
    StaffInvitationRead,
    StaffRoleRead,
    VenueStaffListItem,
    VenueStaffRead,
)

router = APIRouter(prefix="/v1/venue/staff", tags=["venue:staff"])


@router.get(
    "",
    response_model=list[VenueStaffListItem],
    operation_id="venue_staff_list",
    summary="List employees",
    description="Hodimlar, filtered by filial, role and active status.",
)
async def list_staff(
    user: CurrentUser,
    language_id: LanguageId,
    service: StaffServiceDep,
    group_id: Annotated[int, Query(ge=1)],
    venue_id: Annotated[int | None, Query(ge=1)] = None,
    role_id: Annotated[int | None, Query(ge=1)] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> Sequence[VenueStaffListItem]:
    return await service.list_for_group(group_id, language_id, venue_id, role_id, is_active)


@router.get(
    "/counts",
    response_model=StaffCountsRead,
    operation_id="venue_staff_counts",
    summary="Employee counters",
    description="Jami / Aktiv / Noaktiv on the Hodimlar header.",
)
async def staff_counts(
    user: CurrentUser,
    service: StaffServiceDep,
    group_id: Annotated[int, Query(ge=1)],
) -> StaffCountsRead:
    return await service.counts(group_id)


@router.get(
    "/roles",
    response_model=list[StaffRoleRead],
    operation_id="venue_staff_list_roles",
    summary="List roles",
    description="Egasi, Admin, Menendjer, Ofitsant, Oshpaz and the rest.",
)
async def list_roles(
    user: CurrentUser,
    language_id: LanguageId,
    service: StaffServiceDep,
    scope: Annotated[str | None, Query()] = None,
) -> Sequence[StaffRoleRead]:
    return await service.list_roles(language_id, scope)


@router.post(
    "/invitations",
    response_model=StaffInvitationRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="venue_staff_invite",
    summary="Invite an employee",
    description="Xodim qo'shish. The temporary password is sent by SMS once and never returned.",
    dependencies=[require_permission("staff.manage")],
)
async def invite(
    payload: StaffInvitationCreate,
    user: CurrentUser,
    service: StaffServiceDep,
    group_id: Annotated[int, Query(ge=1)],
) -> StaffInvitationRead:
    return await service.invite(user.id, group_id, payload)


@router.post(
    "/invitations/accept",
    response_model=VenueStaffRead,
    operation_id="venue_staff_accept_invitation",
    summary="Accept an invitation",
    description="Redeems the temporary password and sets a chosen one in the same step.",
)
async def accept_invitation(
    payload: InvitationAccept,
    service: StaffServiceDep,
    phone: Annotated[str, Query(min_length=4, max_length=20)],
) -> VenueStaffRead:
    return await service.accept_invitation(payload, phone)


@router.patch(
    "/{staff_id}/active",
    response_model=VenueStaffRead,
    operation_id="venue_staff_set_active",
    summary="Activate or deactivate",
    description="The Active Status toggle on a Hodimlar card.",
    dependencies=[require_permission("staff.manage")],
)
async def set_active(
    user: CurrentUser,
    service: StaffServiceDep,
    staff_id: Annotated[int, Path(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
    is_active: Annotated[bool, Query()],
) -> VenueStaffRead:
    return await service.set_active(user.id, venue_id, staff_id, is_active)
