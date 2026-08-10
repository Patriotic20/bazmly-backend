from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class AuthProvider(StrEnum):
    GOOGLE = "google"


class AuthIdentity(IdIntPk, TimestampMixin, Base):
    """One row per linked social account.

    Still a table rather than a column on `users` even though Google is the only
    provider left: a second one is a row here, and a column would be a migration
    plus a rewrite of every lookup.
    """

    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id"),
        CheckConstraint("provider IN ('google')", name="ck_auth_identities_provider"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_profile: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
