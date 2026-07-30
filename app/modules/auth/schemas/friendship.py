from pydantic import BaseModel

from app.core.schemas import ReadSchema
from app.modules.auth.enums import FriendshipStatus
from app.modules.auth.schemas.user import UserListItem


class FriendshipCreate(BaseModel):
    addressee_id: int


class FriendshipRespond(BaseModel):
    accept: bool


class FriendshipRead(ReadSchema):
    id: int
    requester_id: int
    addressee_id: int
    status: FriendshipStatus


class FriendRead(ReadSchema):
    """The other party of an accepted friendship."""

    user: UserListItem
