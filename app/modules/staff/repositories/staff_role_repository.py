from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.staff.models import (
    Permission,
    StaffRole,
    StaffRolePermission,
)


@dataclass(frozen=True, slots=True)
class StaffRoleWithPermissions:
    role: StaffRole
    permissions: Sequence[Permission]


class StaffRoleRepository:
    """Roles are rows so the seventh ships without a migration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, role_id: int) -> StaffRole | None:
        result = await self.session.execute(select(StaffRole).where(StaffRole.id == role_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> StaffRole | None:
        result = await self.session.execute(select(StaffRole).where(StaffRole.slug == slug))
        return result.scalar_one_or_none()

    async def list_active(self, scope: str | None = None) -> Sequence[StaffRole]:
        stmt = select(StaffRole).where(StaffRole.is_active.is_(True))
        if scope is not None:
            stmt = stmt.where(StaffRole.scope == scope)
        result = await self.session.execute(stmt.order_by(StaffRole.sort_order))
        return list(result.scalars().all())

    async def get_with_permissions(self, role_id: int) -> StaffRoleWithPermissions | None:
        role = await self.get_by_id(role_id)
        if role is None:
            return None
        result = await self.session.execute(
            select(Permission)
            .join(StaffRolePermission, StaffRolePermission.permission_id == Permission.id)
            .where(StaffRolePermission.staff_role_id == role_id)
            .order_by(Permission.slug)
        )
        return StaffRoleWithPermissions(role=role, permissions=result.scalars().all())
