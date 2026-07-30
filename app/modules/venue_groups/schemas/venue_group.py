from pydantic import BaseModel, Field

from app.core.schemas import ReadSchema, UpdateSchema
from app.modules.venue_groups.enums import VenueGroupStatus


class VenueGroupCreate(BaseModel):
    primary_venue_type_id: int
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    logo_url: str | None = None
    default_currency: str = "UZS"


class VenueGroupUpdate(UpdateSchema):
    primary_venue_type_id: int | None = None
    logo_url: str | None = None
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    status: VenueGroupStatus | None = None


class VenueGroupRead(ReadSchema):
    """`logo_url` lives here and nowhere else — a branch has no logo of its own."""

    id: int
    owner_id: int
    primary_venue_type_id: int
    name: str
    description: str | None = None
    logo_url: str | None = None
    default_currency: str
    status: VenueGroupStatus


class BranchListItem(ReadSchema):
    id: int
    name: str
    tagline: str | None = None
    status: str


class VenueGroupWithBranchesRead(ReadSchema):
    group: VenueGroupRead
    branches: list[BranchListItem]
