from collections.abc import Sequence
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, LanguageId, SessionDep
from app.modules.promotions.schemas import (
    BannerRead,
    PromoCodeApply,
    PromoCodePreview,
    UserPromoCodeRead,
)
from app.modules.promotions.services import BannerService, PromoCodeService, VoucherService

router = APIRouter(prefix="/v1", tags=["promotions"])


@router.post(
    "/promo-codes/validate",
    response_model=PromoCodePreview,
    operation_id="promotions_validate_code",
    summary="Check a promo code",
    description="Returns the computed discount without consuming the code.",
)
async def validate_code(
    payload: PromoCodeApply,
    user: CurrentUser,
    session: SessionDep,
    subtotal: Annotated[Decimal, Query(gt=0)],
) -> PromoCodePreview:
    return await PromoCodeService(session).preview(user.id, payload.code, subtotal)


@router.get(
    "/vouchers",
    response_model=list[UserPromoCodeRead],
    operation_id="promotions_list_vouchers",
    summary="My vouchers",
    description="Promokodlar tab. seconds_remaining is computed at read, never stored.",
)
async def list_vouchers(user: CurrentUser, session: SessionDep) -> Sequence[UserPromoCodeRead]:
    return await VoucherService(session).list_for_user(user.id)


@router.get(
    "/banners",
    response_model=list[BannerRead],
    operation_id="promotions_list_banners",
    summary="Active banners",
    description="Eng yaxshi takliflar carousel, inside its scheduling window.",
)
async def list_banners(session: SessionDep, language_id: LanguageId) -> Sequence[BannerRead]:
    return await BannerService(session).list_active(language_id)
