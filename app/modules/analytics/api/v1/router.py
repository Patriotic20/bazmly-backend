"""Dashboard and reports — staff only. Guard: reports.view."""

from collections.abc import Sequence
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, LanguageId, SessionDep, require_permission
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
    summary="Owner home",
    description="Counters, weekday chart, month total, deltas and the live queue.",
    dependencies=[require_permission("reports.view")],
)
async def dashboard(
    user: CurrentUser,
    language_id: LanguageId,
    session: SessionDep,
    group_id: Annotated[int, Query(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
) -> DashboardRead:
    return await DashboardService(session).owner_home(group_id, language_id, venue_id)


@router.get(
    "/daily",
    response_model=list[VenueDailyStatsRead],
    operation_id="venue_analytics_daily",
    summary="Daily rollups",
    description="One row per business date for a filial.",
    dependencies=[require_permission("reports.view")],
)
async def daily(
    user: CurrentUser,
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
    summary="Revenue against the previous period",
    description="Both totals plus the delta, computed at read and never stored.",
    dependencies=[require_permission("reports.view")],
)
async def revenue(
    user: CurrentUser,
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
