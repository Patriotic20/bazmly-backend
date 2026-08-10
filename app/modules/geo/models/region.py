from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class Region(IdIntPk, TimestampMixin, Base):
    """A viloyat: Toshkent, Navoiy, Samarqand, Buxoro."""

    __tablename__ = "regions"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
