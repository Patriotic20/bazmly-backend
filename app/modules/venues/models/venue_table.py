from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class VenueTable(IdIntPk, TimestampMixin, Base):
    """Restaurants only. Individual numbered tables.

    Onboarding collects counts per capacity bucket (2/4/6/8/10+); those are input,
    not state. Expand them into rows at onboarding and never store the buckets.

    There is no `state` column: the board is a left join against live `orders`, so
    nothing can disagree with the orders table.
    """

    __tablename__ = "venue_tables"
    __table_args__ = (UniqueConstraint("venue_id", "number"),)

    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    seats: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    zone_id: Mapped[int | None] = mapped_column(
        ForeignKey("venue_zones.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
