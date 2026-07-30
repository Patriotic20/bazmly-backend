from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class VerificationChannel(StrEnum):
    SMS = "sms"
    EMAIL = "email"


class VerificationPurpose(StrEnum):
    REGISTRATION = "registration"
    LOGIN = "login"
    PHONE_CHANGE = "phone_change"
    EMAIL_CHANGE = "email_change"
    CARD_BINDING = "card_binding"


class VerificationCode(IdIntPk, TimestampMixin, Base):
    """Store the hash, never the code.

    `destination` is denormalized because at registration there is no user row yet.
    The same table serves the card-binding OTP.
    """

    __tablename__ = "verification_codes"
    __table_args__ = (
        Index(
            "ix_verification_codes_destination_purpose_created_at",
            "destination",
            "purpose",
            "created_at",
        ),
        CheckConstraint("channel IN ('sms', 'email')", name="ck_verification_codes_channel"),
        CheckConstraint(
            "purpose IN ('registration', 'login', 'phone_change', 'email_change', 'card_binding')",
            name="ck_verification_codes_purpose",
        ),
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(10), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    attempts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    request_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
