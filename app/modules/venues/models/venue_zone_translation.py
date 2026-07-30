from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class VenueZoneTranslation(IdIntPk, TimestampMixin, Base):
    __tablename__ = "venue_zone_translations"
    __table_args__ = (UniqueConstraint("zone_id", "language_id"),)

    zone_id: Mapped[int] = mapped_column(
        ForeignKey("venue_zones.id", ondelete="CASCADE"), nullable=False
    )
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
