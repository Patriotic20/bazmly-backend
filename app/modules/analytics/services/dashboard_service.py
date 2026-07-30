from datetime import date as date_type
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import NotFoundError
from app.modules.analytics.repositories import VenueDailyStatsRepository
from app.modules.analytics.schemas import DashboardRead, VenueDailyStatsRead, WeekdayBar
from app.modules.analytics.services.analytics_service import AnalyticsService
from app.modules.staff.repositories import VenueStaffRepository
from app.modules.venue_groups.repositories import VenueGroupRepository
from app.modules.venues.repositories import VenueRepository

MONEY = Decimal("0.01")
WEEK_DAYS = 7


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


class DashboardService:
    """The owner-home aggregate.

    The screen mixes chain-level totals with one branch's hours and queue — Part 2
    open question 6. Rather than guess, this returns both ids explicitly so the
    client knows which number belongs to which scope.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.groups = VenueGroupRepository(session)
        self.venues = VenueRepository(session)
        self.staff = VenueStaffRepository(session)
        self.stats = VenueDailyStatsRepository(session)
        self.analytics = AnalyticsService(session)

    async def owner_home(
        self, group_id: int, language_id: int, venue_id: int | None = None
    ) -> DashboardRead:
        now = utcnow_naive()
        today = now.date()

        group_detail = await self.groups.get_with_branches(group_id, language_id)
        if group_detail is None:
            raise NotFoundError("Venue group not found")

        branch_counts = await self.venues.count_by_status_for_group(group_id)
        staff_counts = await self.staff.count_by_active_for_group(group_id)

        scoped_venue_id = venue_id or (
            group_detail.branches[0].venue.id if group_detail.branches else None
        )
        venue_name: str | None = None
        is_open_now = False
        queue_count = 0
        today_row: VenueDailyStatsRead | None = None

        if scoped_venue_id is not None:
            venue_name = next(
                (
                    branch.name
                    for branch in group_detail.branches
                    if branch.venue.id == scoped_venue_id
                ),
                None,
            )
            is_open_now = await self.venues.is_open_at(scoped_venue_id, now)
            queue_count = await self.analytics.live_queue_count(scoped_venue_id, today)
            rows = await self.stats.range_for_venue(scoped_venue_id, today, today)
            if rows:
                today_row = VenueDailyStatsRead.model_validate(rows[0])

        month_start = today.replace(day=1)
        month_totals = await self.stats.sum_for_group(group_id, month_start, today)

        previous_month_end = month_start - timedelta(days=1)
        previous_month_start = previous_month_end.replace(day=1)
        comparison = await self.analytics.compare(
            scoped_venue_id or 0,
            month_start,
            today,
            previous_month_start,
            previous_month_end,
        )

        week = await self._week_bars(scoped_venue_id, today)
        avg_check = (
            _money(month_totals.revenue / month_totals.orders_count)
            if month_totals.orders_count
            else Decimal("0.00")
        )

        return DashboardRead(
            group_id=group_id,
            group_name=group_detail.name,
            venue_id=scoped_venue_id,
            venue_name=venue_name,
            is_open_now=is_open_now,
            branches_total=branch_counts.total,
            branches_active=branch_counts.active,
            branches_closed=branch_counts.closed,
            staff_total=staff_counts.total,
            staff_active=staff_counts.active,
            queue_count=queue_count,
            month_revenue=_money(month_totals.revenue),
            month_bookings=month_totals.bookings_count,
            avg_check=avg_check,
            occupancy_percent=(
                today_row.occupancy_percent if today_row is not None else Decimal("0.00")
            ),
            currency=group_detail.group.default_currency,
            comparison=comparison,
            week=week,
            today=today_row,
        )

    async def _week_bars(self, venue_id: int | None, today: date_type) -> list[WeekdayBar]:
        """Seven bars, always — a day with no rollup row is a zero bar, not a gap."""
        if venue_id is None:
            return []
        start = today - timedelta(days=WEEK_DAYS - 1)
        rows = await self.stats.range_for_venue(venue_id, start, today)
        by_date = {row.business_date: row for row in rows}

        bars: list[WeekdayBar] = []
        for offset in range(WEEK_DAYS):
            day = start + timedelta(days=offset)
            row = by_date.get(day)
            bars.append(
                WeekdayBar(
                    weekday=day.weekday(),
                    bookings_count=row.bookings_count if row else 0,
                    revenue=_money(row.revenue) if row else Decimal("0.00"),
                )
            )
        return bars
