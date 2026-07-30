from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class PaymentKind(StrEnum):
    DEPOSIT = "deposit"
    BALANCE = "balance"
    FULL = "full"
    SUBSCRIPTION = "subscription"


class PaymentStatus(StrEnum):
    CREATED = "created"
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class Payment(IdIntPk, TimestampMixin, Base):
    """The deposit is deducted, not added.

    `kind` separates the deposit from the balance; both rows point at the same
    booking.
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "(booking_id IS NOT NULL)::int + (subscription_id IS NOT NULL)::int = 1",
            name="ck_payments_exactly_one_target",
        ),
        CheckConstraint(
            "kind IN ('deposit', 'balance', 'full', 'subscription')", name="ck_payments_kind"
        ),
        CheckConstraint(
            "status IN ('created', 'pending', 'paid', 'failed', 'refunded')",
            name="ck_payments_status",
        ),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_subscriptions.id"), nullable=True
    )
    card_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_cards.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="UZS", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=PaymentStatus.CREATED, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    failed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
