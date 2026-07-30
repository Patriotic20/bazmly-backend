from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin, utcnow_naive


class OrderItemStatus(StrEnum):
    NEW = "new"
    SENT_TO_KITCHEN = "sent_to_kitchen"
    COOKING = "cooking"
    READY = "ready"
    SERVED = "served"
    CANCELLED = "cancelled"


class OrderItem(IdIntPk, TimestampMixin, Base):
    """Item-level status exists because Oshpaz is a role in this app.

    The kitchen queue is a per-dish question, not a per-check one:
    `order_items WHERE status IN ('sent_to_kitchen', 'cooking')`.

    Prices are snapshotted at insert.
    """

    __tablename__ = "order_items"
    __table_args__ = (
        Index("ix_order_items_order_id_status", "order_id", "status"),
        CheckConstraint(
            "status IN ('new', 'sent_to_kitchen', 'cooking', 'ready', 'served', 'cancelled')",
            name="ck_order_items_status",
        ),
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"), nullable=False)
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("menu_item_variants.id"), nullable=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_name_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=OrderItemStatus.NEW, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_by_staff_id: Mapped[int] = mapped_column(ForeignKey("venue_staff.id"), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utcnow_naive, nullable=False
    )
    served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
