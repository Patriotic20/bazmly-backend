from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin, utcnow_naive


class Receipt(IdIntPk, TimestampMixin, Base):
    """Written once and never updated.

    A correction is a new order or a refund, not an edit. `payload` freezes the
    printed lines so a reprint two months later is byte-identical regardless of
    what happened to the menu.
    """

    __tablename__ = "receipts"

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    receipt_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    printed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utcnow_naive, nullable=False
    )
    printed_by_staff_id: Mapped[int] = mapped_column(ForeignKey("venue_staff.id"), nullable=False)
    fiscal_sign: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fiscal_serial: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reprinted_count: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
