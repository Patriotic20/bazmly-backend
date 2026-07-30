from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.subscriptions.models import UserSubscription, UserSubscriptionStatus


class UserSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, subscription_id: int) -> UserSubscription | None:
        result = await self.session.execute(
            select(UserSubscription).where(UserSubscription.id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def get_active_for_user(self, user_id: int) -> UserSubscription | None:
        result = await self.session.execute(
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.status == UserSubscriptionStatus.ACTIVE,
            )
            .order_by(UserSubscription.current_period_end.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_due_for_renewal(self, now: datetime) -> Sequence[UserSubscription]:
        """Auto-renewing subscriptions whose next payment has come due."""
        result = await self.session.execute(
            select(UserSubscription)
            .where(
                UserSubscription.status == UserSubscriptionStatus.ACTIVE,
                UserSubscription.auto_renew.is_(True),
                UserSubscription.next_payment_at.is_not(None),
                UserSubscription.next_payment_at <= now,
            )
            .order_by(UserSubscription.next_payment_at)
        )
        return result.scalars().all()

    async def mark_past_due(self, subscription_id: int) -> UserSubscription | None:
        result = await self.session.execute(
            update(UserSubscription)
            .where(
                UserSubscription.id == subscription_id,
                UserSubscription.status == UserSubscriptionStatus.ACTIVE,
            )
            .values(status=UserSubscriptionStatus.PAST_DUE)
            .returning(UserSubscription)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def create(self, subscription: UserSubscription) -> UserSubscription:
        self.session.add(subscription)
        await self.session.flush()
        return subscription
