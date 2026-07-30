from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Subquery, case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.localization.models import Language
from app.modules.subscriptions.models import SubscriptionPlan, SubscriptionPlanTranslation


@dataclass(frozen=True, slots=True)
class SubscriptionPlanRow:
    plan: SubscriptionPlan
    name: str
    description: str | None


class SubscriptionPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _translation_subquery(self, language_id: int) -> Subquery:
        priority = case(
            (SubscriptionPlanTranslation.language_id == language_id, 0),
            (Language.code == "uz", 1),
            (Language.code == "en", 2),
            else_=3,
        )
        return (
            select(
                SubscriptionPlanTranslation.plan_id.label("plan_id"),
                SubscriptionPlanTranslation.name.label("name"),
                SubscriptionPlanTranslation.description.label("description"),
            )
            .join(Language, Language.id == SubscriptionPlanTranslation.language_id)
            .distinct(SubscriptionPlanTranslation.plan_id)
            .order_by(SubscriptionPlanTranslation.plan_id, priority)
            .subquery()
        )

    async def get_by_id(self, plan_id: int) -> SubscriptionPlan | None:
        result = await self.session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        )
        return result.scalar_one_or_none()

    async def list_active(self, language_id: int) -> Sequence[SubscriptionPlanRow]:
        translations = self._translation_subquery(language_id)
        result = await self.session.execute(
            select(SubscriptionPlan, translations.c.name, translations.c.description)
            .outerjoin(translations, translations.c.plan_id == SubscriptionPlan.id)
            .where(SubscriptionPlan.is_active.is_(True))
            .order_by(SubscriptionPlan.sort_order)
        )
        return [
            SubscriptionPlanRow(plan=row[0], name=row[1] or row[0].code, description=row[2])
            for row in result.all()
        ]
