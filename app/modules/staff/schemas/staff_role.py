from app.core.schemas import ReadSchema
from app.modules.staff.enums import StaffRoleScope


class StaffRoleRead(ReadSchema):
    id: int
    slug: str
    scope: StaffRoleScope
    name: str
    sort_order: int


class StaffRoleWithPermissionsRead(ReadSchema):
    role: StaffRoleRead
    permission_slugs: list[str]
