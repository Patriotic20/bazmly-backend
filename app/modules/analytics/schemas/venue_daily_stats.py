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
    """Ikkala davr jami va o'qish paytida hisoblangan farq.

    Foiz hech qachon saqlanmaydi: kechikkan bekor qilish kelishi bilan
    saqlangan qiymat noto'g'ri bo'lib qoladi.
    """

    current: StatsTotalsRead
    previous: StatsTotalsRead
    revenue_delta_percent: Decimal | None = None
    bookings_delta_percent: Decimal | None = None
