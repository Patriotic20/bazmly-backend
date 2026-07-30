from app.core.schemas import ReadSchema


class VenueTypeRead(ReadSchema):
    """`name` so'ralgan til uchun allaqachon tanlangan holda qaytariladi."""

    id: int
    slug: str
    name: str
    icon_url: str | None = None
    sort_order: int
