from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin, utcnow_naive


class OrderPaymentMethod(StrEnum):
    CASH = "cash"
    CARD = "card"
    TRANSFER = "transfer"
    CLICK = "click"
    PAYME = "payme"
    OTHER = "other"


class OrderPayment(IdIntPk, TimestampMixin, Base):
    """Split payments are one order, several rows.

    `SUM(amount) >= total_amount` is a service-layer check before the close, not a
    constraint — partial payment on an open check is legal.
    """

    __tablename__ = "order_payments"
    __table_args__ = (
        CheckConstraint(
            "method IN ('cash', 'card', 'transfer', 'click', 'payme', 'other')",
            name="ck_order_payments_method",
        ),
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="UZS", nullable=False)
    received_by_staff_id: Mapped[int] = mapped_column(ForeignKey("venue_staff.id"), nullable=False)
    paid_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utcnow_naive, nullable=False
    )
    provider_transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    change_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
