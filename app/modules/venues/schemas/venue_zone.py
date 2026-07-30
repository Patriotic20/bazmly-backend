from pydantic import BaseModel, Field

from app.core.schemas import ReadSchema


class VenueZoneCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = 0


class VenueZoneRead(ReadSchema):
    """ "Umumiy" is a UI shortcut meaning no zone filter — never a row, so never
    part of this list."""

    id: int
    slug: str
    name: str
    sort_order: int
