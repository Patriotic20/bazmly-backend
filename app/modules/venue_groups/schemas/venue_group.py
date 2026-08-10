from pydantic import BaseModel, Field

from app.core.schemas import ReadSchema, UpdateSchema
from app.modules.venue_groups.enums import VenueGroupStatus
from app.modules.venues.enums import VenueTypeSlug
from app.modules.venues.schemas import VenueCreate


class VenueGroupCreate(BaseModel):
    primary_venue_type: VenueTypeSlug
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    logo_url: str | None = None
    default_currency: str = "UZS"


class VenueGroupWithBranchCreate(BaseModel):
    """Tarmoq va uning birinchi filiali — bitta so'rovda.

    Ajratilmaydi, chunki `venues.venue_group_id` NOT NULL: ikki so'rov oralig'ida
    filialsiz tarmoq holati paydo bo'lardi, va uni tozalash kimningdir ishi
    bo'lib qolardi.
    """

    group: VenueGroupCreate
    branch: VenueCreate


class VenueGroupUpdate(UpdateSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    primary_venue_type: VenueTypeSlug | None = None
    logo_url: str | None = None
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    status: VenueGroupStatus | None = None


class VenueGroupRead(ReadSchema):
    """`logo_url` faqat shu yerda saqlanadi — filialning o'z logotipi yo'q."""

    id: int
    owner_id: int
    primary_venue_type: VenueTypeSlug
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
