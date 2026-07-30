from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.staff.models import Permission, StaffRolePermission, VenueStaff


@dataclass(frozen=True, slots=True)
class StaffCounts:
    """The Hodimlar header: Jami / Aktiv / Noaktiv."""

    total: int
    active: int
    inactive: int


class VenueStaffRepository:
    """Employment, not identity. Credentials live on `users`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, staff_id: int) -> VenueStaff | None:
        result = await self.session.execute(select(VenueStaff).where(VenueStaff.id == staff_id))
        return result.scalar_one_or_none()

    async def list_for_group(
        self,
        group_id: int,
        venue_id: int | None = None,
        role_id: int | None = None,
        is_active: bool | None = None,
    ) -> Sequence[VenueStaff]:
        stmt = select(VenueStaff).where(VenueStaff.venue_group_id == group_id)
        if venue_id is not None:
            stmt = stmt.where(VenueStaff.venue_id == venue_id)
        if role_id is not None:
            stmt = stmt.where(VenueStaff.staff_role_id == role_id)
        if is_active is not None:
            stmt = stmt.where(VenueStaff.is_active.is_(is_active))
        result = await self.session.execute(stmt.order_by(VenueStaff.id))
        return result.scalars().all()

    async def get_for_user_and_venue(self, user_id: int, venue_id: int) -> VenueStaff | None:
        result = await self.session.execute(
            select(VenueStaff).where(VenueStaff.user_id == user_id, VenueStaff.venue_id == venue_id)
        )
        return result.scalar_one_or_none()

    async def count_by_active_for_group(self, group_id: int) -> StaffCounts:
        """One grouped pass. It must be exact, and at 45 rows it is cheap."""
        result = await self.session.execute(
            select(VenueStaff.is_active, func.count())
            .where(VenueStaff.venue_group_id == group_id)
            .group_by(VenueStaff.is_active)
        )
        counts = {bool(is_active): int(count) for is_active, count in result.all()}
        active = counts.get(True, 0)
        inactive = counts.get(False, 0)
        return StaffCounts(total=active + inactive, active=active, inactive=inactive)

    async def has_permission(self, user_id: int, venue_id: int, permission_slug: str) -> bool:
        """One join from `venue_staff` through `staff_role_permissions` to
        `permissions`, answered by the database.

        A group-scoped row (`venue_id IS NULL`) is an owner or admin and carries its
        permissions at every branch in the chain, which is why the venue predicate
        is an OR rather than an equality.
        """
        exists_stmt = (
            select(VenueStaff.id)
            .join(
                StaffRolePermission,
                StaffRolePermission.staff_role_id == VenueStaff.staff_role_id,
            )
            .join(Permission, Permission.id == StaffRolePermission.permission_id)
            .where(
                VenueStaff.user_id == user_id,
                VenueStaff.is_active.is_(True),
                Permission.slug == permission_slug,
                or_(VenueStaff.venue_id == venue_id, VenueStaff.venue_id.is_(None)),
            )
            .exists()
        )
        result = await self.session.execute(select(exists_stmt))
        return bool(result.scalar_one())

    async def create(self, staff: VenueStaff) -> VenueStaff:
        self.session.add(staff)
        await self.session.flush()
        return staff

    async def set_active(self, staff_id: int, is_active: bool, now: datetime) -> VenueStaff | None:
        values: dict[str, object] = {"is_active": is_active}
        values["deactivated_at"] = None if is_active else now
        if is_active:
            values["activated_at"] = now
        result = await self.session.execute(
            update(VenueStaff)
            .where(VenueStaff.id == staff_id)
            .values(**values)
            .returning(VenueStaff)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def list_for_user(self, user_id: int) -> Sequence[VenueStaff]:
        """Every employment row a person holds — one per branch they work at."""
        result = await self.session.execute(
            select(VenueStaff)
            .where(VenueStaff.user_id == user_id, VenueStaff.is_active.is_(True))
            .order_by(VenueStaff.id)
        )
        return result.scalars().all()
