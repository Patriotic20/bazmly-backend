from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class BookingItem(IdIntPk, TimestampMixin, Base):
    """Restaurant menu pre-order from the Menu step of the wizard.

    Prices and names are snapshotted at confirmation — never rebuild an old
    receipt by joining to live `menu_items`.
    """

    __tablename__ = "booking_items"

    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
