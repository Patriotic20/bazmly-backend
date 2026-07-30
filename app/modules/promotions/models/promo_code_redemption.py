from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin, utcnow_naive


class PromoCodeRedemption(IdIntPk, TimestampMixin, Base):
    """One row per actual use.

    `booking_id` and `subscription_id` point at tables created in later revisions,
    so their foreign keys are added by the bookings and payments migrations rather
    than the promotions one.
    """

    __tablename__ = "promo_code_redemptions"

    promo_code_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_subscriptions.id"), nullable=True
    )
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    redeemed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utcnow_naive, nullable=False
    )
