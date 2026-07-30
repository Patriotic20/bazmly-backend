from app.core.schemas import ReadSchema


class AmenityRead(ReadSchema):
    id: int
    slug: str
    name: str
    icon_url: str | None = None
    sort_order: int
