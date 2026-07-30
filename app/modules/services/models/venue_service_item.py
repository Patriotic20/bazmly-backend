from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class VenueServiceItem(IdIntPk, TimestampMixin, Base):
    """The Taomlar rows nested under Dasturxon tuzash.

    Not `menu_items` — these are the fixed contents of a wedding table sold as one
    package, not a-la-carte dishes with photos, variants and per-branch availability.
    """

    __tablename__ = "venue_service_items"

    venue_service_id: Mapped[int] = mapped_column(
        ForeignKey("venue_services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
