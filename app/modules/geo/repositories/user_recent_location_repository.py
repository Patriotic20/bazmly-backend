from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.modules.geo.models import UserRecentLocation

RECENT_LOCATION_CAP = 10


class UserRecentLocationRepository:
    """Backs "Oxirgi manzillar", capped at ten rows per user."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(
        self, user_id: int, limit: int = RECENT_LOCATION_CAP
    ) -> Sequence[UserRecentLocation]:
        result = await self.session.execute(
            select(UserRecentLocation)
            .where(UserRecentLocation.user_id == user_id)
            .order_by(UserRecentLocation.last_used_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def upsert(
        self,
        user_id: int,
        district_id: int,
        label: str,
        latitude: Decimal,
        longitude: Decimal,
    ) -> UserRecentLocation:
        """Touch `last_used_at` if this district is already remembered, else insert.

        Matched on (user_id, district_id) rather than the label, so re-picking the
        same district with a different label moves the existing row up instead of
        creating a near-duplicate.
        """
        result = await self.session.execute(
            select(UserRecentLocation).where(
                UserRecentLocation.user_id == user_id,
                UserRecentLocation.district_id == district_id,
            )
        )
        existing = result.scalar_one_or_none()
        now = utcnow_naive()

        if existing is not None:
            existing.label = label
            existing.latitude = latitude
            existing.longitude = longitude
            existing.last_used_at = now
            await self.session.flush()
            return existing

        location = UserRecentLocation(
            user_id=user_id,
            district_id=district_id,
            label=label,
            latitude=latitude,
            longitude=longitude,
            last_used_at=now,
        )
        self.session.add(location)
        await self.session.flush()
        return location

    async def trim_to_limit(self, user_id: int, keep: int = RECENT_LOCATION_CAP) -> int:
        """Delete everything past the newest `keep` rows. Returns rows removed."""
        keep_ids = (
            select(UserRecentLocation.id)
            .where(UserRecentLocation.user_id == user_id)
            .order_by(UserRecentLocation.last_used_at.desc())
            .limit(keep)
            .scalar_subquery()
        )
        result = await self.session.execute(
            delete(UserRecentLocation)
            .where(
                UserRecentLocation.user_id == user_id,
                UserRecentLocation.id.notin_(keep_ids),
            )
            .returning(UserRecentLocation.id)
        )
        await self.session.flush()
        return len(result.scalars().all())
