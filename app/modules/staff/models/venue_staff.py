from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin, utcnow_naive


class VenueStaff(IdIntPk, TimestampMixin, Base):
    """Employment: who works where, as what. Not identity, and not credentials.

    `login`, `password_hash` and `must_change_password` live on `users` — one
    person may hold two employment rows at two branches, and credentials belong to
    the identity.

    `role_scope` is denormalized from `staff_roles.scope` and kept honest by the
    composite foreign key below. A plain CHECK cannot read another table, so this
    is what makes "a venue-scoped role requires a venue" enforceable in Postgres
    rather than in application code.
    """

    __tablename__ = "venue_staff"
    __table_args__ = (
        UniqueConstraint("venue_id", "user_id"),
        ForeignKeyConstraint(
            ["staff_role_id", "role_scope"],
            ["staff_roles.id", "staff_roles.scope"],
            name="fk_venue_staff_role_scope",
        ),
        CheckConstraint(
            "role_scope <> 'venue' OR venue_id IS NOT NULL",
            name="ck_venue_staff_venue_scope_requires_venue",
        ),
        CheckConstraint("role_scope IN ('group', 'venue')", name="ck_venue_staff_role_scope"),
        Index("ix_venue_staff_venue_group_id_is_active", "venue_group_id", "is_active"),
        Index("ix_venue_staff_venue_id_staff_role_id", "venue_id", "staff_role_id"),
    )

    venue_group_id: Mapped[int] = mapped_column(ForeignKey("venue_groups.id"), nullable=False)
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    staff_role_id: Mapped[int] = mapped_column(nullable=False)
    role_scope: Mapped[str] = mapped_column(String(10), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    invited_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    invited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utcnow_naive, nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
