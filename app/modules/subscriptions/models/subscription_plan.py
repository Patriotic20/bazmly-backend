from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class SubscriptionPlanCode(StrEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubscriptionPlan(IdIntPk, TimestampMixin, Base):
    __tablename__ = "subscription_plans"
    __table_args__ = (
        CheckConstraint("code IN ('monthly', 'yearly')", name="ck_subscription_plans_code"),
    )

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="UZS", nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    benefit_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
