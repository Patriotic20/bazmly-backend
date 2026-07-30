from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class CardBrand(StrEnum):
    HUMO = "humo"
    UZCARD = "uzcard"
    VISA = "visa"
    MASTERCARD = "mastercard"


class PaymentCard(IdIntPk, TimestampMixin, Base):
    """Never store the PAN.

    The add-card form collects number + MM/YY, sends them straight to the provider,
    and persists only the returned token.
    """

    __tablename__ = "payment_cards"
    __table_args__ = (
        CheckConstraint(
            "brand IN ('humo', 'uzcard', 'visa', 'mastercard')", name="ck_payment_cards_brand"
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_token: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str] = mapped_column(String(20), nullable=False)
    last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    holder_name: Mapped[str] = mapped_column(String(200), nullable=False)
    expiry_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    expiry_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
