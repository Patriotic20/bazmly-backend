from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class VenuePhoto(IdIntPk, TimestampMixin, Base):
    """Max 5 per venue (`MAX_VENUE_PHOTOS`) — enforced by the schema, not the database.

    The first by `sort_order` is the cover; the set is always replaced whole.
    """

    __tablename__ = "venue_photos"

    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
