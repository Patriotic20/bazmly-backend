from decimal import Decimal

from app.core.schemas import Money, ReadSchema
from app.modules.analytics.schemas.venue_daily_stats import (
    PeriodComparisonRead,
    VenueDailyStatsRead,
)


class WeekdayBar(ReadSchema):
    """Haftalik grafikning bir ustuni."""

    weekday: int
    bookings_count: int
    revenue: Money


class DashboardRead(ReadSchema):
    """Boshqaruv panelining yig'ma ma'lumoti.

    `group_name` tarmoqqa tegishli; `is_open_now` va `queue_count` esa panel
    ko'rsatayotgan filialga. Shu sababli ikkalasining identifikatori ham
    alohida qaytariladi.
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
