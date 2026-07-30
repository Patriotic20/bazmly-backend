from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class VenueGuestTier(IdIntPk, TimestampMixin, Base):
    """To'yxona only: 100-150 / 150-200 / 200-300 / 300+, each with a base price."""

    __tablename__ = "venue_guest_tiers"

    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    min_guests: Mapped[int] = mapped_column(Integer, nullable=False)
    max_guests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
