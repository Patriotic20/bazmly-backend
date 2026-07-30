from decimal import Decimal

from app.core.schemas import Money, ReadSchema
from app.modules.analytics.schemas.venue_daily_stats import (
    PeriodComparisonRead,
    VenueDailyStatsRead,
)


class WeekdayBar(ReadSchema):
    """One bar of the weekday chart."""

    weekday: int
    bookings_count: int
    revenue: Money


class DashboardRead(ReadSchema):
    """The owner-home aggregate.

    `group_name` is the chain; `is_open_now` and `queue_count` belong to the
    branch the dashboard is scoped to. Open question 6 in Part 2 notes that the
    screen mixes the two, so both carry an explicit id here.
    """

    group_id: int
    group_name: str
    venue_id: int | None = None
    venue_name: str | None = None
    is_open_now: bool = False
    branches_total: int
    branches_active: int
    branches_closed: int
    staff_total: int
    staff_active: int
    queue_count: int
    month_revenue: Money
    month_bookings: int
    avg_check: Money
    occupancy_percent: Decimal
    currency: str
    comparison: PeriodComparisonRead
    week: list[WeekdayBar]
    today: VenueDailyStatsRead | None = None
