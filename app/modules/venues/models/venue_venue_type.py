from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base


class VenueVenueType(Base):
    """Many-to-many: a venue can be Restoran and To'yxona at once.

    Pure association table — composite PK, no surrogate id, no timestamps.
    """

    __tablename__ = "venue_venue_types"

    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), primary_key=True
    )
    venue_type_id: Mapped[int] = mapped_column(
        ForeignKey("venue_types.id", ondelete="CASCADE"), primary_key=True
    )
