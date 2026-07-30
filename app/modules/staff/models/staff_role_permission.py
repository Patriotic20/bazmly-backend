from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base


class StaffRolePermission(Base):
    """Which role may do what.

    Pure association table — composite PK, no surrogate id, no timestamps.
    """

    __tablename__ = "staff_role_permissions"

    staff_role_id: Mapped[int] = mapped_column(
        ForeignKey("staff_roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )
