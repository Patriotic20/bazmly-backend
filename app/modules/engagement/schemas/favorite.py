from pydantic import BaseModel

from app.core.schemas import ReadSchema
from app.modules.venues.schemas import VenueListItem


class FavoriteCreate(BaseModel):
    venue_id: int


class FavoriteRead(ReadSchema):
    id: int
    venue: VenueListItem


class FavoriteToggled(ReadSchema):
    venue_id: int
    is_favorite: bool
