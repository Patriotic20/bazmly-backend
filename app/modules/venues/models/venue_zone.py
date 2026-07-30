from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class VenueZone(IdIntPk, TimestampMixin, Base):
    """Seeded per branch with `ichkari` and `tashqari`.

    "Umumiy" is a UI shortcut meaning no zone filter, not a zone row — the same
    pattern as "Barchasi" in the venue-type picker. A terrace-only kafe and a
    three-floor restaurant cannot share a fixed enum, so zones are rows.
    """

    __tablename__ = "venue_zones"

    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(50), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
