from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class StaffRoleScope(StrEnum):
    GROUP = "group"
    VENUE = "venue"


class StaffRole(IdIntPk, TimestampMixin, Base):
    """Roles are rows, so the seventh ships without a migration.

    The `UNIQUE (id, scope)` is not redundant with the primary key: it is the
    target of the composite foreign key on `venue_staff`, which is what lets a
    plain CHECK there enforce "a venue-scoped role requires a venue".
    """

    __tablename__ = "staff_roles"
    __table_args__ = (
        UniqueConstraint("id", "scope", name="uq_staff_roles_id_scope"),
        CheckConstraint("scope IN ('group', 'venue')", name="ck_staff_roles_scope"),
    )

    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
