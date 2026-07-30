from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.subscriptions.enums import SubscriptionPlanCode
from app.modules.subscriptions.repositories import (
    SubscriptionPlanRepository,
    UserSubscriptionRepository,
)
from app.modules.subscriptions.schemas import SubscriptionPlanRead, UserSubscriptionRead


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.plans = SubscriptionPlanRepository(session)
        self.subscriptions = UserSubscriptionRepository(session)

    async def list_plans(self, language_id: int) -> Sequence[SubscriptionPlanRead]:
        rows = await self.plans.list_active(language_id)
        return [
            SubscriptionPlanRead(
                id=row.plan.id,
                code=SubscriptionPlanCode(row.plan.code),
                name=row.name,
                description=row.description,
                price=row.plan.price,
                currency=row.plan.currency,
                duration_days=row.plan.duration_days,
                benefit_percent=row.plan.benefit_percent,
                sort_order=row.plan.sort_order,
            )
            for row in rows
        ]

    async def active_for_user(self, user_id: int) -> UserSubscriptionRead | None:
        subscription = await self.subscriptions.get_active_for_user(user_id)
        return (
            UserSubscriptionRead.model_validate(subscription) if subscription is not None else None
        )

    async def benefit_percent_in_transaction(self, user_id: int) -> Decimal:
        """The subscriber discount applied on top of any promo code.

        Zero when there is no active subscription, so callers can add it
        unconditionally instead of branching.
        """
        subscription = await self.subscriptions.get_active_for_user(user_id)
        if subscription is None:
            return Decimal("0")
        plan = await self.plans.get_by_id(subscription.plan_id)
        return Decimal(plan.benefit_percent) if plan is not None else Decimal("0")

    async def mark_past_due(self, subscription_id: int) -> UserSubscriptionRead | None:
        updated = await self.subscriptions.mark_past_due(subscription_id)
        await self.session.commit()
        return UserSubscriptionRead.model_validate(updated) if updated else None
