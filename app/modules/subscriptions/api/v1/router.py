from collections.abc import Sequence

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, LanguageId, SessionDep
from app.modules.subscriptions.schemas import SubscriptionPlanRead, UserSubscriptionRead
from app.modules.subscriptions.services import SubscriptionService

router = APIRouter(prefix="/v1/subscriptions", tags=["subscriptions"])


@router.get(
    "/plans",
    response_model=list[SubscriptionPlanRead],
    operation_id="subscriptions_list_plans",
    summary="Tariflar ro'yxati",
    description="Oylik va yillik tariflar, obunachi chegirmasi foizi bilan.",
)
async def list_plans(
    session: SessionDep, language_id: LanguageId
) -> Sequence[SubscriptionPlanRead]:
    return await SubscriptionService(session).list_plans(language_id)


@router.get(
    "/me",
    response_model=UserSubscriptionRead | None,
    operation_id="subscriptions_get_mine",
    summary="Mening obunam",
    description="Aktiv obuna bo'lmasa, `null` qaytariladi.",
)
async def get_mine(user: CurrentUser, session: SessionDep) -> UserSubscriptionRead | None:
    return await SubscriptionService(session).active_for_user(user.id)
