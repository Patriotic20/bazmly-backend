from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.core.dependencies import CurrentUser, SessionDep
from app.modules.auth.api.dependencies import (
    DeviceServiceDep,
    FriendshipServiceDep,
    UserServiceDep,
)
from app.modules.auth.schemas import (
    DeviceCreate,
    DeviceRead,
    FriendshipCreate,
    FriendshipRead,
    FriendshipRespond,
    UserListItem,
    UserProfileUpdate,
    UserRead,
)
from app.modules.geo.schemas import UserAddressCreate, UserAddressRead
from app.modules.geo.services import LocationService

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserRead,
    operation_id="users_get_me",
    summary="Profil ma'lumoti",
    description="Sozlamalar ekranidagi profil kartasi shu yo'ldan o'qiydi.",
)
async def get_me(user: CurrentUser, service: UserServiceDep) -> UserRead:
    return await service.get_profile(user.id)


@router.patch(
    "/me",
    response_model=UserRead,
    operation_id="users_update_me",
    summary="Profilni tahrirlash",
    description="Bo'sh so'rov rad etiladi — jimgina hech narsa qilmaslik o'rniga.",
)
async def update_me(
    payload: UserProfileUpdate, user: CurrentUser, service: UserServiceDep
) -> UserRead:
    return await service.update_profile(user.id, payload)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    operation_id="users_delete_me",
    summary="Akkauntni o'chirish",
    description="Yumshoq o'chirish: bronlar va to'lovlar hisobot uchun saqlanib qoladi.",
)
async def delete_me(user: CurrentUser, service: UserServiceDep) -> None:
    await service.delete_account(user.id)


@router.get(
    "/me/devices",
    response_model=list[DeviceRead],
    operation_id="users_list_devices",
    summary="Qurilmalar ro'yxati",
    description="Bildirishnoma yuborilishi mumkin bo'lgan qurilmalar.",
)
async def list_devices(user: CurrentUser, service: DeviceServiceDep) -> Sequence[DeviceRead]:
    return await service.list_for_user(user.id)


@router.post(
    "/me/devices",
    response_model=DeviceRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="users_register_device",
    summary="Qurilmani ro'yxatga olish",
    description="Bir xil `device_uuid` qayta yuborilsa, push token o'rnida yangilanadi.",
)
async def register_device(
    payload: DeviceCreate, user: CurrentUser, service: DeviceServiceDep
) -> DeviceRead:
    return await service.register(user.id, payload)


@router.get(
    "/me/friends",
    response_model=list[UserListItem],
    operation_id="users_list_friends",
    summary="Do'stlar ro'yxati",
    description="Qabul qilingan har bir do'stlikning ikkinchi tomoni.",
)
async def list_friends(user: CurrentUser, service: FriendshipServiceDep) -> Sequence[UserListItem]:
    return await service.list_friends(user.id)


@router.get(
    "/me/friend-requests",
    response_model=list[FriendshipRead],
    operation_id="users_list_friend_requests",
    summary="Kelgan so'rovlar",
    description="Kirgan foydalanuvchidan javob kutayotgan do'stlik so'rovlari.",
)
async def list_friend_requests(
    user: CurrentUser, service: FriendshipServiceDep
) -> Sequence[FriendshipRead]:
    return await service.list_incoming(user.id)


@router.post(
    "/me/friends",
    response_model=FriendshipRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="users_request_friend",
    summary="Do'stlik so'rovi yuborish",
    description="Profil ekranidagi Do'st qo'shish tugmasi uchun.",
)
async def request_friend(
    payload: FriendshipCreate, user: CurrentUser, service: FriendshipServiceDep
) -> FriendshipRead:
    return await service.request(user.id, payload.addressee_id)


@router.post(
    "/me/friends/{friendship_id}/accept",
    response_model=FriendshipRead,
    operation_id="users_accept_friend",
    summary="So'rovga javob berish",
    description="Faqat so'rov yuborilgan foydalanuvchi javob bera oladi.",
)
async def accept_friend(
    payload: FriendshipRespond,
    user: CurrentUser,
    service: FriendshipServiceDep,
    friendship_id: Annotated[int, Path(ge=1)],
) -> FriendshipRead:
    return await service.respond(user.id, friendship_id, payload)


@router.get(
    "/me/recent-locations",
    response_model=list[UserAddressRead],
    operation_id="users_list_recent_locations",
    summary="Oxirgi manzillar",
    description="Eng yangisidan boshlab, ko'pi bilan o'nta.",
)
async def list_recent_locations(
    user: CurrentUser, session: SessionDep
) -> Sequence[UserAddressRead]:
    return await LocationService(session).list_recent(user.id)


@router.post(
    "/me/recent-locations",
    response_model=UserAddressRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="users_remember_location",
    summary="Manzilni saqlash",
    description="Bir tuman qayta tanlansa, mavjud yozuv nusxalanmay yuqoriga ko'chadi.",
)
async def remember_location(
    payload: UserAddressCreate, user: CurrentUser, session: SessionDep
) -> UserAddressRead:
    return await LocationService(session).remember(user.id, payload)
