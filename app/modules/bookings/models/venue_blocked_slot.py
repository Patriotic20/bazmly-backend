from datetime import date as date_type
from datetime import time
from enum import StrEnum

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class BlockedSlotReason(StrEnum):
    MANUAL = "manual"
    MAINTENANCE = "maintenance"
    PRIVATE_EVENT = "private_event"


class VenueBlockedSlot(IdIntPk, TimestampMixin, Base):
    """Feeds availability, which is computed and never materialized."""

    __tablename__ = "venue_blocked_slots"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('manual', 'maintenance', 'private_event')",
            name="ck_venue_blocked_slots_reason",
        ),
    )

    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    table_id: Mapped[int | None] = mapped_column(
        ForeignKey("venue_tables.id", ondelete="CASCADE"), nullable=True
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    reason: Mapped[str] = mapped_column(String(30), nullable=False)
