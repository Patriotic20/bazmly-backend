from app.core.schemas import ReadSchema


class ServiceCatalogRead(ReadSchema):
    """Platforma belgilagan yopiq ro'yxat: Dasturxon tuzash, Raqqoslar, Kartej va boshqalar."""

    id: int
    slug: str
    name: str
    icon_url: str | None = None
    applies_to_venue_type_id: int | None = None
    sort_order: int
