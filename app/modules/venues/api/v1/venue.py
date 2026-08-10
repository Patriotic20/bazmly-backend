"""Staff-facing venue routes — Filiallar.

Separate from `customer.py` on purpose: an owner listing their branches and a
guest searching venues want different payloads and different filters. Branching on
role inside one endpoint would make the response shape depend on the caller, which
no generated client can express.
"""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.core.dependencies import CurrentUser, require_group_permission, require_permission
from app.modules.auth.schemas import UserRead
from app.modules.venues.api.dependencies import (
    OnboardingServiceDep,
    VenueServiceDep,
    VenueTableServiceDep,
)
from app.modules.venues.schemas import (
    TableCountsCreate,
    VenueCreate,
    VenueRead,
    VenueStatusCountsRead,
    VenueTableRead,
    VenueUpdate,
    VenueZoneRead,
    WorkingHoursReplace,
)

router = APIRouter(prefix="/v1/venue/venues", tags=["venue:venues"])


@router.post(
    "",
    response_model=VenueRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="venue_venues_create",
    summary="Filial qo'shish",
    description=(
        "Tarmoqqa yangi filial. Ruxsat `group_id` bo'yicha tekshiriladi, chunki "
        "yaratilayotgan filialning `venue_id` si hali mavjud emas. Egasi tarmoqdan "
        "meros qoladi, joylashuv koordinatalardan hisoblanadi, `ichkari` va "
        "`tashqari` zonalari avtomatik ochiladi."
    ),
    dependencies=[require_group_permission("branch.create")],
)
async def create_branch(
    payload: VenueCreate,
    service: OnboardingServiceDep,
    group_id: Annotated[int, Query(ge=1)],
) -> VenueRead:
    return await service.add_branch(group_id, payload)


@router.get(
    "",
    response_model=list[VenueRead],
    operation_id="venue_venues_list",
    summary="Filiallar ro'yxati",
    description="Kirgan egasining tarmog'idagi filiallar.",
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
    summary="Filial hisoblagichlari",
    description="Filiallar sarlavhasidagi Jami / Aktiv / Yopiq, bitta guruhlangan so'rovda.",
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
    summary="Filial ma'lumoti",
    description="Filialning egasi ko'radigan ma'lumoti.",
)
async def get_branch(
    service: VenueServiceDep,
    venue_id: Annotated[int, Path(ge=1)],
    user: CurrentUser,
) -> VenueRead:
    detail = await service.get_detail(venue_id)
    return detail.venue


@router.patch(
    "/{venue_id}",
    response_model=VenueRead,
    operation_id="venue_venues_update",
    summary="Filialni tahrirlash",
    description="Manzil, sig'im, oldindan to'lov shartlari va bron uchun oldindan xabar muddati.",
)
async def update_branch(
    payload: VenueUpdate,
    user: Annotated[UserRead, require_permission("branch.manage")],
    service: VenueServiceDep,
    venue_id: Annotated[int, Path(ge=1)],
) -> VenueRead:
    return await service.update_details(user.id, venue_id, payload)


@router.put(
    "/{venue_id}/working-hours",
    response_model=VenueRead,
    operation_id="venue_venues_replace_working_hours",
    summary="Ish vaqtini yangilash",
    description=(
        "Yettala kun qayta yoziladi, shunda olib tashlangan kun eski qator bo'lib qolmaydi."
    ),
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
    summary="Stollar ro'yxati",
    description="Buyurtmalar taxtasi uchun raqamlangan stollar.",
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
    summary="Stollarni sig'im bo'yicha yaratish",
    description="Boshlang'ich sozlashdagi 2/4/6/8/10+ guruhlari raqamlangan stollarga yoyiladi.",
)
async def create_tables_bulk(
    payload: TableCountsCreate,
    user: Annotated[UserRead, require_permission("branch.manage")],
    service: VenueTableServiceDep,
    venue_id: Annotated[int, Path(ge=1)],
) -> Sequence[VenueTableRead]:
    return await service.create_from_counts(user.id, venue_id, payload)


@router.get(
    "/{venue_id}/zones",
    response_model=list[VenueZoneRead],
    operation_id="venue_venues_list_zones",
    summary="Zonalar ro'yxati",
    description="Ichkari va Tashqari — Stollar taxtasidagi filtr uchun.",
)
async def list_zones(
    user: CurrentUser,
    service: VenueTableServiceDep,
    venue_id: Annotated[int, Path(ge=1)],
) -> Sequence[VenueZoneRead]:
    return await service.list_zones(venue_id)


@router.patch(
    "/{venue_id}/onboarding/address",
    response_model=VenueRead,
    operation_id="venue_venues_onboarding_address",
    summary="Boshlang'ich sozlash: manzil",
    description="`onboarding_step` ni oshiradi, shunda tugallanmagan sozlash davom ettiriladi.",
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
    summary="Boshlang'ich sozlash: stollar",
    description="Stollar bosqichi tugallangan deb belgilanadi.",
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
    summary="Boshlang'ich sozlash: xizmatlar",
    description="Qo'shimcha xizmatlar bosqichi tugallangan deb belgilanadi.",
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
    summary="Boshlang'ich sozlash: media",
    description="Media va vizual bosqichi tugallangan deb belgilanadi.",
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
    summary="Nashr qilish",
    description="Filial ishga tushadi: status `active` va `onboarded_at` yoziladi.",
    dependencies=[require_permission("branch.manage")],
)
async def onboarding_finish(
    service: OnboardingServiceDep, venue_id: Annotated[int, Path(ge=1)]
) -> VenueRead:
    return await service.finish(venue_id)
