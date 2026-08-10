"""Dashboard and reports — staff only. Guard: reports.view."""

from collections.abc import Sequence
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.dependencies import SessionDep, require_permission
from app.modules.analytics.schemas import (
    DashboardRead,
    PeriodComparisonRead,
    VenueDailyStatsRead,
)
from app.modules.analytics.services import AnalyticsService, DashboardService

router = APIRouter(prefix="/v1/venue/analytics", tags=["venue:analytics"])


@router.get(
    "/dashboard",
    response_model=DashboardRead,
    operation_id="venue_analytics_dashboard",
    summary="Boshqaruv paneli",
    description="Hisoblagichlar, haftalik grafik, oylik jami, o'zgarish va jonli navbat.",
    dependencies=[require_permission("reports.view")],
)
async def dashboard(
    session: SessionDep,
    group_id: Annotated[int, Query(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
) -> DashboardRead:
    return await DashboardService(session).owner_home(group_id, venue_id)


@router.get(
    "/daily",
    response_model=list[VenueDailyStatsRead],
    operation_id="venue_analytics_daily",
    summary="Kunlik hisobot",
    description="Filialning har bir ish kuni uchun bitta qator.",
    dependencies=[require_permission("reports.view")],
)
async def daily(
    session: SessionDep,
    venue_id: Annotated[int, Query(ge=1)],
    date_from: Annotated[date, Query()],
    date_to: Annotated[date, Query()],
) -> Sequence[VenueDailyStatsRead]:
    return await AnalyticsService(session).range_for_venue(venue_id, date_from, date_to)


@router.get(
    "/revenue",
    response_model=PeriodComparisonRead,
    operation_id="venue_analytics_revenue",
    summary="Tushum taqqoslash",
    description=(
        "Ikkala davr jami va ular orasidagi farq — farq o'qish paytida hisoblanadi, saqlanmaydi."
    ),
    dependencies=[require_permission("reports.view")],
)
async def revenue(
    session: SessionDep,
    venue_id: Annotated[int, Query(ge=1)],
    current_from: Annotated[date, Query()],
    current_to: Annotated[date, Query()],
    previous_from: Annotated[date, Query()],
    previous_to: Annotated[date, Query()],
) -> PeriodComparisonRead:
    return await AnalyticsService(session).compare(
        venue_id, current_from, current_to, previous_from, previous_to
    )
