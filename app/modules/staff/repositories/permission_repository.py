from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.staff.models import Permission, StaffRolePermission


class PermissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_slug(self, slug: str) -> Permission | None:
        result = await self.session.execute(select(Permission).where(Permission.slug == slug))
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[Permission]:
        result = await self.session.execute(
            select(Permission).order_by(Permission.group, Permission.slug)
        )
        return result.scalars().all()

    async def list_slugs_for_role(self, role_id: int) -> Sequence[str]:
        result = await self.session.execute(
            select(Permission.slug)
            .join(StaffRolePermission, StaffRolePermission.permission_id == Permission.id)
            .where(StaffRolePermission.staff_role_id == role_id)
            .order_by(Permission.slug)
        )
        return list(result.scalars().all())
