from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.staff.models import StaffInvitation


class StaffInvitationRepository:
    """Stores the hash of the temporary password, never the password."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, invitation: StaffInvitation) -> StaffInvitation:
        self.session.add(invitation)
        await self.session.flush()
        return invitation

    async def get_by_id(self, invitation_id: int) -> StaffInvitation | None:
        result = await self.session.execute(
            select(StaffInvitation).where(StaffInvitation.id == invitation_id)
        )
        return result.scalar_one_or_none()

    async def get_active_by_phone(self, phone: str, now: datetime) -> StaffInvitation | None:
        """Newest unaccepted, unrevoked, unexpired invite. Uses the
        `(phone, expires_at)` index that also backs invite throttling."""
        result = await self.session.execute(
            select(StaffInvitation)
            .where(
                StaffInvitation.phone == phone,
                StaffInvitation.accepted_at.is_(None),
                StaffInvitation.revoked_at.is_(None),
                StaffInvitation.expires_at > now,
            )
            .order_by(StaffInvitation.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def accept(self, invitation_id: int, now: datetime) -> StaffInvitation | None:
        """Guarded so a forwarded SMS cannot be redeemed twice."""
        result = await self.session.execute(
            update(StaffInvitation)
            .where(
                StaffInvitation.id == invitation_id,
                StaffInvitation.accepted_at.is_(None),
                StaffInvitation.revoked_at.is_(None),
                StaffInvitation.expires_at > now,
            )
            .values(accepted_at=now)
            .returning(StaffInvitation)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def revoke(self, invitation_id: int, now: datetime) -> StaffInvitation | None:
        result = await self.session.execute(
            update(StaffInvitation)
            .where(StaffInvitation.id == invitation_id, StaffInvitation.revoked_at.is_(None))
            .values(revoked_at=now)
            .returning(StaffInvitation)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def expire_stale(self, now: datetime) -> Sequence[int]:
        """Bulk-revoke invites past their expiry. Returns the affected ids."""
        result = await self.session.execute(
            update(StaffInvitation)
            .where(
                StaffInvitation.accepted_at.is_(None),
                StaffInvitation.revoked_at.is_(None),
                StaffInvitation.expires_at <= now,
            )
            .values(revoked_at=now)
            .returning(StaffInvitation.id)
        )
        await self.session.flush()
        return list(result.scalars().all())
