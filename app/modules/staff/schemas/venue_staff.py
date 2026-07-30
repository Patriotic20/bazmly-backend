from datetime import datetime

from pydantic import BaseModel

from app.core.schemas import ReadSchema, UpdateSchema
from app.modules.auth.schemas import UserListItem


class VenueStaffCreate(BaseModel):
    venue_id: int | None = None
    user_id: int
    staff_role_id: int


class VenueStaffUpdate(UpdateSchema):
    staff_role_id: int | None = None
    is_active: bool | None = None


class VenueStaffListItem(ReadSchema):
    """A Hodimlar card. No credentials — those live on `users` and never ship."""

    id: int
    venue_id: int | None = None
    staff_role_id: int
    role_name: str
    is_active: bool
    user: UserListItem


class VenueStaffRead(ReadSchema):
    id: int
    venue_group_id: int
    venue_id: int | None = None
    user_id: int
    staff_role_id: int
    role_scope: str
    is_active: bool
    invited_at: datetime
    activated_at: datetime | None = None
    deactivated_at: datetime | None = None


class StaffCountsRead(ReadSchema):
    """Jami / Aktiv / Noaktiv."""

    total: int
    active: int
    inactive: int
