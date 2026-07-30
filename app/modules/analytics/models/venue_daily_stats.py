from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin, utcnow_naive


class VenueDailyStats(IdIntPk, TimestampMixin, Base):
    """Nightly rollup, refreshed incrementally for today on order close.

    Running the dashboard's weekday chart and month totals over raw `bookings` and
    `orders` on each app open is a full scan per owner per refresh.

    Deltas ("+12%") are computed at read, not stored — storing one means storing it
    wrong the moment a late cancellation lands.
    """

    __tablename__ = "venue_daily_stats"
    __table_args__ = (UniqueConstraint("venue_id", "business_date"),)

    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    business_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    bookings_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    guests_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    no_show_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancelled_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    avg_check: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    occupancy_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utcnow_naive, nullable=False
    )
