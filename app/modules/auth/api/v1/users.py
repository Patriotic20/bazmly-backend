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
    summary="Get the signed-in profile",
    description="Sozlamalar reads this for the profile card.",
)
async def get_me(user: CurrentUser, service: UserServiceDep) -> UserRead:
    return await service.get_profile(user.id)


@router.patch(
    "/me",
    response_model=UserRead,
    operation_id="users_update_me",
    summary="Update the profile",
    description="A body with no fields set is rejected rather than silently doing nothing.",
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
    summary="Delete the account",
    description="Akkauntni o'chirish. Soft delete: bookings and payments survive for accounting.",
)
async def delete_me(user: CurrentUser, service: UserServiceDep) -> None:
    await service.delete_account(user.id)


@router.get(
    "/me/devices",
    response_model=list[DeviceRead],
    operation_id="users_list_devices",
    summary="List registered devices",
    description="Devices that may receive push notifications.",
)
async def list_devices(user: CurrentUser, service: DeviceServiceDep) -> Sequence[DeviceRead]:
    return await service.list_for_user(user.id)


@router.post(
    "/me/devices",
    response_model=DeviceRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="users_register_device",
    summary="Register a device",
    description="Re-registering the same device uuid updates its push token in place.",
)
async def register_device(
    payload: DeviceCreate, user: CurrentUser, service: DeviceServiceDep
) -> DeviceRead:
    return await service.register(user.id, payload)


@router.get(
    "/me/friends",
    response_model=list[UserListItem],
    operation_id="users_list_friends",
    summary="List accepted friends",
    description="The other party of every accepted friendship, in either direction.",
)
async def list_friends(user: CurrentUser, service: FriendshipServiceDep) -> Sequence[UserListItem]:
    return await service.list_friends(user.id)


@router.get(
    "/me/friend-requests",
    response_model=list[FriendshipRead],
    operation_id="users_list_friend_requests",
    summary="List incoming friend requests",
    description="Requests awaiting an answer from the signed-in user.",
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
    summary="Send a friend request",
    description="Backs the Add friends button on the profile screen.",
)
async def request_friend(
    payload: FriendshipCreate, user: CurrentUser, service: FriendshipServiceDep
) -> FriendshipRead:
    return await service.request(user.id, payload.addressee_id)


@router.post(
    "/me/friends/{friendship_id}/accept",
    response_model=FriendshipRead,
    operation_id="users_accept_friend",
    summary="Answer a friend request",
    description="Only the addressee may answer.",
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
    summary="List recent addresses",
    description="Oxirgi manzillar, newest first, capped at ten.",
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
    summary="Remember an address",
    description="Re-picking a district moves the existing entry up rather than duplicating it.",
)
async def remember_location(
    payload: UserAddressCreate, user: CurrentUser, session: SessionDep
) -> UserAddressRead:
    return await LocationService(session).remember(user.id, payload)
