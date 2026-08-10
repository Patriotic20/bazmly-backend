from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class StaffInvitation(IdIntPk, TimestampMixin, Base):
    """A pending employment offer, redeemed with a temporary password.

    The row stores only the hash. The plaintext is returned once, in the response
    to the request that created the invitation, and the owner passes it to the
    person themselves — there is no delivery channel left to send it down. It
    expires, and `users.must_change_password` forces rotation on first login, so
    a forwarded credential is not a permanent key to the till.
    """

    __tablename__ = "staff_invitations"
    __table_args__ = (Index("ix_staff_invitations_phone_expires_at", "phone", "expires_at"),)

    venue_group_id: Mapped[int] = mapped_column(ForeignKey("venue_groups.id"), nullable=False)
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), nullable=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    staff_role_id: Mapped[int] = mapped_column(ForeignKey("staff_roles.id"), nullable=False)
    temp_password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
