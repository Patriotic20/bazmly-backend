from app.core.schemas import ReadSchema


class VenueTypeRead(ReadSchema):
    """`name` is already resolved for the requested language."""

    id: int
    slug: str
    name: str
    icon_url: str | None = None
    sort_order: int
