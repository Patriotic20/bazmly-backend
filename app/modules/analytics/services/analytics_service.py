from collections.abc import Sequence
from datetime import date as date_type
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.repositories import (
    PeriodComparison,
    StatsTotals,
    VenueDailyStatsRepository,
)
from app.modules.analytics.schemas import (
    PeriodComparisonRead,
    StatsTotalsRead,
    VenueDailyStatsRead,
)
from app.modules.bookings.enums import BookingStatus
from app.modules.bookings.repositories import BookingRepository

MONEY = Decimal("0.01")
PERCENT = Decimal("100")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


class AnalyticsService:
    """Rollups for the dashboard.

    Deltas are computed at read from two period totals and never stored: "+12%" is
    this period against the previous one, and a stored percentage becomes wrong the
    moment a late cancellation lands.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.stats = VenueDailyStatsRepository(session)
        self.bookings = BookingRepository(session)

    async def rollup_day(
        self, venue_id: int, business_date: date_type, **metrics: Any
    ) -> VenueDailyStatsRead:
        """Idempotent by construction — the repository upserts on
        `(venue_id, business_date)`, so a re-run for a date cannot double its
        numbers and today's row can be refreshed on every order close.
        """
        row = await self.stats.upsert(venue_id, business_date, **metrics)
        await self.session.commit()
        return VenueDailyStatsRead.model_validate(row)

    async def range_for_venue(
        self, venue_id: int, date_from: date_type, date_to: date_type
    ) -> Sequence[VenueDailyStatsRead]:
        rows = await self.stats.range_for_venue(venue_id, date_from, date_to)
        return [VenueDailyStatsRead.model_validate(row) for row in rows]

    async def sum_for_group(
        self, group_id: int, date_from: date_type, date_to: date_type
    ) -> StatsTotalsRead:
        totals = await self.stats.sum_for_group(group_id, date_from, date_to)
        return self._to_totals_read(totals)

    async def compare(
        self,
        venue_id: int,
        current_from: date_type,
        current_to: date_type,
        previous_from: date_type,
        previous_to: date_type,
    ) -> PeriodComparisonRead:
        comparison = await self.stats.compare_periods(
            venue_id, current_from, current_to, previous_from, previous_to
        )
        return self._to_comparison_read(comparison)

    async def live_queue_count(self, venue_id: int, day: date_type) -> int:
        """ "Hozirgi navbat" — today's confirmed bookings that have not checked in.

        Live, not a rollup: the whole point of the number is that it changes as
        guests arrive.
        """
        bookings = await self.bookings.list_for_venue_day(venue_id, day, [BookingStatus.CONFIRMED])
        return sum(1 for booking in bookings if booking.checked_in_at is None)

    def _to_totals_read(self, totals: StatsTotals) -> StatsTotalsRead:
        return StatsTotalsRead(
            bookings_count=totals.bookings_count,
            guests_count=totals.guests_count,
            no_show_count=totals.no_show_count,
            cancelled_count=totals.cancelled_count,
            orders_count=totals.orders_count,
            revenue=_money(totals.revenue),
        )

    def _to_comparison_read(self, comparison: PeriodComparison) -> PeriodComparisonRead:
        return PeriodComparisonRead(
            current=self._to_totals_read(comparison.current),
            previous=self._to_totals_read(comparison.previous),
            revenue_delta_percent=self._delta(
                comparison.current.revenue, comparison.previous.revenue
            ),
            bookings_delta_percent=self._delta(
                Decimal(comparison.current.bookings_count),
                Decimal(comparison.previous.bookings_count),
            ),
        )

    def _delta(self, current: Decimal, previous: Decimal) -> Decimal | None:
        """`None` when there is no baseline.

        Growth from zero is not "+100%" — it is undefined, and reporting a number
        there would invent a trend from a single data point.
        """
        if previous == 0:
            return None
        return ((current - previous) / previous * PERCENT).quantize(MONEY, rounding=ROUND_HALF_UP)
