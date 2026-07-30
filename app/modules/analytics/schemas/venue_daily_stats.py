from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import Money, ReadSchema


class VenueDailyStatsRead(ReadSchema):
    id: int
    venue_id: int
    business_date: date
    bookings_count: int
    guests_count: int
    no_show_count: int
    cancelled_count: int
    orders_count: int
    revenue: Money
    avg_check: Money
    occupancy_percent: Decimal
    computed_at: datetime


class StatsTotalsRead(ReadSchema):
    bookings_count: int
    guests_count: int
    no_show_count: int
    cancelled_count: int
    orders_count: int
    revenue: Money


class PeriodComparisonRead(ReadSchema):
    """Both totals plus the delta the service computed at read.

    The percentage is never stored: "+12%" is this period against the previous
    one, and storing it means storing it wrong the moment a late cancellation
    lands.
    """

    current: StatsTotalsRead
    previous: StatsTotalsRead
    revenue_delta_percent: Decimal | None = None
    bookings_delta_percent: Decimal | None = None
