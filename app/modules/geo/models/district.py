from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class District(IdIntPk, TimestampMixin, Base):
    """Holds both tuman and shahar rows — one level, one table.

    The Figma calls this "Shahar" on the owner form and "Tuman" on the customer
    form; the API name is district.
    """

    __tablename__ = "districts"

    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
