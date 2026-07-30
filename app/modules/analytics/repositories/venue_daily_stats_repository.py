from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.modules.analytics.models import VenueDailyStats
from app.modules.venues.models import Venue


@dataclass(frozen=True, slots=True)
class StatsTotals:
    bookings_count: int
    guests_count: int
    no_show_count: int
    cancelled_count: int
    orders_count: int
    revenue: Decimal


@dataclass(frozen=True, slots=True)
class PeriodComparison:
    """Both totals, so the service computes the percentage.

    The delta is deliberately not computed or stored here: "+12%" is this period
    against the previous one, and storing it means storing it wrong the moment a
    late cancellation lands.
    """

    current: StatsTotals
    previous: StatsTotals


_METRIC_COLUMNS = (
    "bookings_count",
    "guests_count",
    "no_show_count",
    "cancelled_count",
    "orders_count",
    "revenue",
    "avg_check",
    "occupancy_percent",
)


class VenueDailyStatsRepository:
    """Nightly rollup, refreshed for today on order close."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self, venue_id: int, business_date: date_type, **metrics: Any
    ) -> VenueDailyStats:
        """`INSERT ... ON CONFLICT (venue_id, business_date) DO UPDATE`.

        Idempotent by construction, so the nightly job can be re-run for a date
        without doubling its numbers, and today's row can be refreshed on every
        order close.
        """
        values: dict[str, Any] = {
            "venue_id": venue_id,
            "business_date": business_date,
            "computed_at": utcnow_naive(),
        }
        values.update({k: v for k, v in metrics.items() if k in _METRIC_COLUMNS})

        stmt = pg_insert(VenueDailyStats).values(**values)
        update_set = {
            column: stmt.excluded[column]
            for column in (*_METRIC_COLUMNS, "computed_at")
            if column in values or column == "computed_at"
        }
        result = await self.session.execute(
            stmt.on_conflict_do_update(
                index_elements=[VenueDailyStats.venue_id, VenueDailyStats.business_date],
                set_=update_set,
            ).returning(VenueDailyStats)
        )
        await self.session.flush()
        return result.scalars().one()

    async def range_for_venue(
        self, venue_id: int, date_from: date_type, date_to: date_type
    ) -> Sequence[VenueDailyStats]:
        result = await self.session.execute(
            select(VenueDailyStats)
            .where(
                VenueDailyStats.venue_id == venue_id,
                VenueDailyStats.business_date >= date_from,
                VenueDailyStats.business_date <= date_to,
            )
            .order_by(VenueDailyStats.business_date)
        )
        return result.scalars().all()

    async def sum_for_group(
        self, group_id: int, date_from: date_type, date_to: date_type
    ) -> StatsTotals:
        """Chain-level numbers are a SUM across the group's branches."""
        result = await self.session.execute(
            select(
                func.coalesce(func.sum(VenueDailyStats.bookings_count), 0),
                func.coalesce(func.sum(VenueDailyStats.guests_count), 0),
                func.coalesce(func.sum(VenueDailyStats.no_show_count), 0),
                func.coalesce(func.sum(VenueDailyStats.cancelled_count), 0),
                func.coalesce(func.sum(VenueDailyStats.orders_count), 0),
                func.coalesce(func.sum(VenueDailyStats.revenue), 0),
            )
            .select_from(VenueDailyStats)
            .join(Venue, Venue.id == VenueDailyStats.venue_id)
            .where(
                Venue.venue_group_id == group_id,
                VenueDailyStats.business_date >= date_from,
                VenueDailyStats.business_date <= date_to,
            )
        )
        return _to_totals(result.one())

    async def _totals_for_venue(
        self, venue_id: int, date_from: date_type, date_to: date_type
    ) -> StatsTotals:
        result = await self.session.execute(
            select(
                func.coalesce(func.sum(VenueDailyStats.bookings_count), 0),
                func.coalesce(func.sum(VenueDailyStats.guests_count), 0),
                func.coalesce(func.sum(VenueDailyStats.no_show_count), 0),
                func.coalesce(func.sum(VenueDailyStats.cancelled_count), 0),
                func.coalesce(func.sum(VenueDailyStats.orders_count), 0),
                func.coalesce(func.sum(VenueDailyStats.revenue), 0),
            ).where(
                VenueDailyStats.venue_id == venue_id,
                VenueDailyStats.business_date >= date_from,
                VenueDailyStats.business_date <= date_to,
            )
        )
        return _to_totals(result.one())

    async def compare_periods(
        self,
        venue_id: int,
        current_from: date_type,
        current_to: date_type,
        previous_from: date_type,
        previous_to: date_type,
    ) -> PeriodComparison:
        return PeriodComparison(
            current=await self._totals_for_venue(venue_id, current_from, current_to),
            previous=await self._totals_for_venue(venue_id, previous_from, previous_to),
        )


def _to_totals(row: Any) -> StatsTotals:
    return StatsTotals(
        bookings_count=int(row[0]),
        guests_count=int(row[1]),
        no_show_count=int(row[2]),
        cancelled_count=int(row[3]),
        orders_count=int(row[4]),
        revenue=Decimal(row[5]),
    )
