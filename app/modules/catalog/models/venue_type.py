from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class VenueType(IdIntPk, TimestampMixin, Base):
    """restoran / toyxona / kafe.

    "Barchasi" in the picker is a UI shortcut that selects every type, not a row.
    """

    __tablename__ = "venue_types"

    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    icon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
