from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin, utcnow_naive


class VenueTableQr(IdIntPk, TimestampMixin, Base):
    """The printed standee a customer scans to open that table's menu.

    Opposite direction from `bookings.qr_token`, which the customer shows to the
    venue. Different lifecycles — do not merge them.
    """

    __tablename__ = "venue_table_qrs"

    table_id: Mapped[int] = mapped_column(
        ForeignKey("venue_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    printed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utcnow_naive, nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
