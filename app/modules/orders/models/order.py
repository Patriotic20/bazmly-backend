from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin, utcnow_naive


class OrderKind(StrEnum):
    DINE_IN = "dine_in"
    TAKEAWAY = "takeaway"


class OrderStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    SERVED = "served"
    AWAITING_PAYMENT = "awaiting_payment"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Order(IdIntPk, TimestampMixin, Base):
    """An open check on a table right now. Not a booking.

    A booking is a promise made before arrival; most orders belong to walk-ins who
    never booked. `booking_id` links the two when a booked guest sits down.

    `business_date` is set at open from the branch's day-close rule and is not
    derived from `opened_at`: a venue serving past midnight needs the previous
    business day.

    The elapsed timers on the cards are `now() - opened_at`, computed at render.
    One open check per table is enforced by a partial unique index added in the
    migration, so two waiters cannot open the same table twice.
    """

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("venue_id", "business_date", "order_number"),
        # One open check per table. Two waiters tapping the same empty table
        # produce one check and one integrity error.
        Index(
            "one_open_order_per_table",
            "table_id",
            unique=True,
            postgresql_where=text(
                "table_id IS NOT NULL AND status NOT IN ('completed', 'cancelled')"
            ),
        ),
        Index("ix_orders_venue_id_status_opened_at", "venue_id", "status", "opened_at"),
        Index("ix_orders_venue_id_business_date", "venue_id", "business_date"),
        CheckConstraint("kind IN ('dine_in', 'takeaway')", name="ck_orders_kind"),
        CheckConstraint(
            "status IN ('open', 'in_progress', 'served', 'awaiting_payment',"
            " 'completed', 'cancelled')",
            name="ck_orders_status",
        ),
    )

    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), nullable=False)
    table_id: Mapped[int | None] = mapped_column(ForeignKey("venue_tables.id"), nullable=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    order_number: Mapped[int] = mapped_column(Integer, nullable=False)
    business_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default=OrderKind.DINE_IN, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.OPEN, nullable=False)
    guests_count: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    waiter_staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("venue_staff.id", ondelete="SET NULL"), nullable=True
    )
    opened_by_staff_id: Mapped[int] = mapped_column(ForeignKey("venue_staff.id"), nullable=False)
    closed_by_staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("venue_staff.id", ondelete="SET NULL"), nullable=True
    )

    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    service_charge: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="UZS", nullable=False)

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utcnow_naive, nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
