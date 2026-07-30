from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class UserPromoCodeSource(StrEnum):
    SIGNUP = "signup"
    CAMPAIGN = "campaign"
    COMPENSATION = "compensation"


class UserPromoCodeStatus(StrEnum):
    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"


class UserPromoCode(IdIntPk, TimestampMixin, Base):
    """The Voucher tab.

    The countdown is `expires_at - now()` computed at render — never stored.
    """

    __tablename__ = "user_promo_codes"
    __table_args__ = (
        Index("ix_user_promo_codes_user_id_status_expires_at", "user_id", "status", "expires_at"),
        CheckConstraint(
            "source IN ('signup', 'campaign', 'compensation')",
            name="ck_user_promo_codes_source",
        ),
        CheckConstraint(
            "status IN ('active', 'used', 'expired')", name="ck_user_promo_codes_status"
        ),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    promo_code_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=UserPromoCodeStatus.ACTIVE, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
