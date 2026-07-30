from app.core.schemas import ReadSchema


class PermissionRead(ReadSchema):
    id: int
    slug: str
    group: str
