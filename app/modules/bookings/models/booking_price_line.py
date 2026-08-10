from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class PriceLineType(StrEnum):
    HALL_RENTAL = "hall_rental"
    CATERING = "catering"
    SERVICE_LOGISTICS = "service_logistics"
    DEPOSIT = "deposit"


class BookingPriceLine(IdIntPk, TimestampMixin, Base):
    """Backs the "Detailed Price Report". Frozen at confirmation."""

    __tablename__ = "booking_price_lines"
    __table_args__ = (
        CheckConstraint(
            "line_type IN ('hall_rental', 'catering', 'service_logistics', 'deposit')",
            name="ck_booking_price_lines_type",
        ),
    )

    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    line_type: Mapped[str] = mapped_column(String(30), nullable=False)
    label_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
