from app.core.schemas import ReadSchema


class RegionRead(ReadSchema):
    id: int
    name: str
    code: str
