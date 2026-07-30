from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base


class VenueAmenity(Base):
    """Many-to-many venue ↔ amenity.

    Pure association table — composite PK, no surrogate id, no timestamps.
    """

    __tablename__ = "venue_amenities"

    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), primary_key=True
    )
    amenity_id: Mapped[int] = mapped_column(
        ForeignKey("amenities.id", ondelete="CASCADE"), primary_key=True
    )
