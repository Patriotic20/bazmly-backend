from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class UserRole(StrEnum):
    CUSTOMER = "customer"
    VENUE_OWNER = "venue_owner"
    VENUE_STAFF = "venue_staff"
    MODERATOR = "moderator"
    ADMIN = "admin"


class UserStatus(StrEnum):
    PENDING_PROFILE = "pending_profile"
    ACTIVE = "active"
    BLOCKED = "blocked"
    DELETED = "deleted"


class UserTheme(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class User(IdIntPk, TimestampMixin, Base):
    """A person. Staff are users too — employment lives in `venue_staff`.

    Credentials (`login`, `password_hash`, `must_change_password`) sit here rather
    than on `venue_staff` because one person may hold two employment rows at two
    branches; credentials belong to the identity, not the employment.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "phone IS NOT NULL OR email IS NOT NULL",
            name="ck_users_phone_or_email",
        ),
        CheckConstraint(
            "role IN ('customer', 'venue_owner', 'venue_staff', 'moderator', 'admin')",
            name="ck_users_role",
        ),
        CheckConstraint(
            "status IN ('pending_profile', 'active', 'blocked', 'deleted')",
            name="ck_users_status",
        ),
        CheckConstraint("theme IN ('system', 'light', 'dark')", name="ck_users_theme"),
    )

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.CUSTOMER, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=UserStatus.PENDING_PROFILE, nullable=False
    )
    theme: Mapped[str] = mapped_column(String(10), default=UserTheme.SYSTEM, nullable=False)

    # `login` is staff-only and issued by an invitation. `password_hash` is not:
    # a customer may set one at registration, and then it is what `/auth/login`
    # checks against their phone number. Null means the phone alone signs in.
    login: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
