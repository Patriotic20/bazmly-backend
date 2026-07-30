from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class DiscountType(StrEnum):
    PERCENT = "percent"
    FIXED = "fixed"


class PromoAppliesTo(StrEnum):
    BOOKING = "booking"
    SUBSCRIPTION = "subscription"
    BOTH = "both"


class PromoCode(IdIntPk, TimestampMixin, Base):
    """`used_count` is recomputed by the owning service on write. No DB triggers."""

    __tablename__ = "promo_codes"
    __table_args__ = (
        CheckConstraint("discount_type IN ('percent', 'fixed')", name="ck_promo_codes_type"),
        CheckConstraint(
            "applies_to IN ('booking', 'subscription', 'both')",
            name="ck_promo_codes_applies_to",
        ),
    )

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    discount_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    applies_to: Mapped[str] = mapped_column(String(20), nullable=False)
    min_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    max_discount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    usage_limit_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_limit_per_user: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
