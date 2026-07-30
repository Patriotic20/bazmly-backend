from typing import Annotated

from fastapi import Depends

from app.core.dependencies import SessionDep
from app.modules.auth.services import (
    AuthService,
    DeviceService,
    FriendshipService,
    UserService,
)


def get_auth_service(session: SessionDep) -> AuthService:
    return AuthService(session)


def get_user_service(session: SessionDep) -> UserService:
    return UserService(session)


def get_device_service(session: SessionDep) -> DeviceService:
    return DeviceService(session)


def get_friendship_service(session: SessionDep) -> FriendshipService:
    return FriendshipService(session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
DeviceServiceDep = Annotated[DeviceService, Depends(get_device_service)]
FriendshipServiceDep = Annotated[FriendshipService, Depends(get_friendship_service)]
