from app.core.schemas import ReadSchema
from app.modules.venues.enums import VenueTypeSlug


class ServiceCatalogRead(ReadSchema):
    """Platforma belgilagan yopiq ro'yxat: Dasturxon tuzash, Raqqoslar, Kartej va boshqalar."""

    id: int
    slug: str
    name: str
    icon_url: str | None = None
    applies_to_venue_type: VenueTypeSlug | None = None
    sort_order: int
