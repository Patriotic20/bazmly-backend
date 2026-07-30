from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class Amenity(IdIntPk, TimestampMixin, Base):
    """parking, sound system, stage, air conditioning, professional kitchen, Wi-Fi."""

    __tablename__ = "amenities"

    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    icon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
