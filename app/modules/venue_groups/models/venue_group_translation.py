from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class VenueGroupTranslation(IdIntPk, TimestampMixin, Base):
    """The group name — "Tinchlik Plaza" in the dashboard header.

    Branch names live in `venue_translations`.
    """

    __tablename__ = "venue_group_translations"
    __table_args__ = (UniqueConstraint("venue_group_id", "language_id"),)

    venue_group_id: Mapped[int] = mapped_column(
        ForeignKey("venue_groups.id", ondelete="CASCADE"), nullable=False
    )
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
