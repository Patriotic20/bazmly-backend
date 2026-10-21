"""Hodimlar — staff only."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.core.dependencies import CurrentUser, VerifiedGroupId, require_permission
from app.modules.auth.schemas import UserRead
from app.modules.staff.api.dependencies import StaffServiceDep
from app.modules.staff.schemas import (
    InvitationAccept,
    StaffCountsRead,
    StaffInvitationCreate,
    StaffInvitationCreated,
    StaffRoleRead,
    VenueStaffListItem,
    VenueStaffRead,
)

router = APIRouter(prefix="/v1/venue/staff", tags=["venue:staff"])


@router.get(
    "",
    response_model=list[VenueStaffListItem],
    operation_id="venue_staff_list",
    summary="Hodimlar ro'yxati",
    description="Filial, rol va faollik holati bo'yicha filtrlanadi.",
)
async def list_staff(
    user: CurrentUser,
    service: StaffServiceDep,
    group_id: VerifiedGroupId,
    venue_id: Annotated[int | None, Query(ge=1)] = None,
    role_id: Annotated[int | None, Query(ge=1)] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> Sequence[VenueStaffListItem]:
    return await service.list_for_group(group_id, venue_id, role_id, is_active)


@router.get(
    "/counts",
    response_model=StaffCountsRead,
    operation_id="venue_staff_counts",
    summary="Hodim hisoblagichlari",
    description="Hodimlar sarlavhasidagi Jami / Aktiv / Noaktiv.",
)
async def staff_counts(
    user: CurrentUser,
    service: StaffServiceDep,
    group_id: VerifiedGroupId,
) -> StaffCountsRead:
    return await service.counts(group_id)


@router.get(
    "/roles",
    response_model=list[StaffRoleRead],
    operation_id="venue_staff_list_roles",
    summary="Rollar ro'yxati",
    description="Egasi, Admin, Menendjer, Ofitsant, Oshpaz va boshqalar.",
)
async def list_roles(
    user: CurrentUser,
    service: StaffServiceDep,
    scope: Annotated[str | None, Query()] = None,
) -> Sequence[StaffRoleRead]:
    return await service.list_roles(scope)


@router.post(
    "/invitations",
    response_model=StaffInvitationCreated,
    status_code=status.HTTP_201_CREATED,
    operation_id="venue_staff_invite",
    summary="Hodim qo'shish",
    description=(
        "Login va vaqtinchalik parol **faqat shu javobda** qaytariladi — ularni "
        "hodimga o'zingiz yetkazasiz. Boshqa hech qayerdan qayta o'qib bo'lmaydi."
    ),
)
async def invite(
    payload: StaffInvitationCreate,
    user: Annotated[UserRead, require_permission("staff.manage")],
    service: StaffServiceDep,
    group_id: Annotated[int, Query(ge=1)],
) -> StaffInvitationCreated:
    return await service.invite(user.id, group_id, payload)


@router.post(
    "/invitations/accept",
    response_model=VenueStaffRead,
    operation_id="venue_staff_accept_invitation",
    summary="Taklifnomani qabul qilish",
    description="Vaqtinchalik parol ishlatiladi va shu bosqichda yangi parol o'rnatiladi.",
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
    summary="Faollikni o'zgartirish",
    description="Hodimlar kartasidagi faollik tugmasi.",
)
async def set_active(
    user: Annotated[UserRead, require_permission("staff.manage")],
    service: StaffServiceDep,
    staff_id: Annotated[int, Path(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
    is_active: Annotated[bool, Query()],
) -> VenueStaffRead:
    return await service.set_active(user.id, venue_id, staff_id, is_active)
