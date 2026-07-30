from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Subquery, case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.localization.models import Language
from app.modules.staff.models import (
    Permission,
    StaffRole,
    StaffRolePermission,
    StaffRoleTranslation,
)


@dataclass(frozen=True, slots=True)
class StaffRoleRow:
    role: StaffRole
    name: str


@dataclass(frozen=True, slots=True)
class StaffRoleWithPermissions:
    role: StaffRole
    permissions: Sequence[Permission]


class StaffRoleRepository:
    """Roles are rows so the seventh ships without a migration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _translation_subquery(self, language_id: int) -> Subquery:
        priority = case(
            (StaffRoleTranslation.language_id == language_id, 0),
            (Language.code == "uz", 1),
            (Language.code == "en", 2),
            else_=3,
        )
        return (
            select(
                StaffRoleTranslation.staff_role_id.label("staff_role_id"),
                StaffRoleTranslation.name.label("name"),
            )
            .join(Language, Language.id == StaffRoleTranslation.language_id)
            .distinct(StaffRoleTranslation.staff_role_id)
            .order_by(StaffRoleTranslation.staff_role_id, priority)
            .subquery()
        )

    async def get_by_id(self, role_id: int) -> StaffRole | None:
        result = await self.session.execute(select(StaffRole).where(StaffRole.id == role_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> StaffRole | None:
        result = await self.session.execute(select(StaffRole).where(StaffRole.slug == slug))
        return result.scalar_one_or_none()

    async def list_active(
        self, language_id: int, scope: str | None = None
    ) -> Sequence[StaffRoleRow]:
        translations = self._translation_subquery(language_id)
        stmt = (
            select(StaffRole, translations.c.name)
            .outerjoin(translations, translations.c.staff_role_id == StaffRole.id)
            .where(StaffRole.is_active.is_(True))
        )
        if scope is not None:
            stmt = stmt.where(StaffRole.scope == scope)
        result = await self.session.execute(stmt.order_by(StaffRole.sort_order))
        return [StaffRoleRow(role=row[0], name=row[1] or row[0].slug) for row in result.all()]

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
