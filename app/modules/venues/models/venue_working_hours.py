from datetime import time

from sqlalchemy import Boolean, ForeignKey, SmallInteger, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class VenueWorkingHours(IdIntPk, TimestampMixin, Base):
    """Seven rows per venue. Drives the "Ochiq" badge, computed at render."""

    __tablename__ = "venue_working_hours"

    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    opens_at: Mapped[time | None] = mapped_column(Time, nullable=True)
    closes_at: Mapped[time | None] = mapped_column(Time, nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
