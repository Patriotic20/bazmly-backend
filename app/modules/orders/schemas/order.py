from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.schemas import Money, ReadSchema, UpdateSchema
from app.modules.orders.enums import OrderKind, OrderStatus
from app.modules.orders.schemas.order_item import OrderItemRead
from app.modules.orders.schemas.order_payment import OrderPaymentRead


class OrderOpen(BaseModel):
    table_id: int
    guests_count: int | None = Field(default=None, gt=0)
    kind: OrderKind = OrderKind.DINE_IN


class OrderUpdate(UpdateSchema):
    guests_count: int | None = Field(default=None, gt=0)
    waiter_staff_id: int | None = None


class OrderCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class OrderListItem(ReadSchema):
    """A Buyurtmalar card. `elapsed_seconds` is `now - opened_at`, computed by the
    service at read — the timer on the card is never a stored number."""

    id: int
    order_number: int
    table_id: int | None = None
    table_number: int | None = None
    status: OrderStatus
    kind: OrderKind
    guests_count: int | None = None
    total_amount: Money
    currency: str
    opened_at: datetime
    elapsed_seconds: int = 0


class OrderRead(ReadSchema):
    id: int
    venue_id: int
    table_id: int | None = None
    booking_id: int | None = None
    order_number: int
    business_date: date
    kind: OrderKind
    status: OrderStatus
    guests_count: int | None = None
    waiter_staff_id: int | None = None
    subtotal: Money
    discount_amount: Money
    service_charge: Money
    total_amount: Money
    currency: str
    opened_at: datetime
    closed_at: datetime | None = None
    cancelled_at: datetime | None = None


class OrderDetailRead(ReadSchema):
    order: OrderRead
    items: list[OrderItemRead] = Field(default_factory=list)
    payments: list[OrderPaymentRead] = Field(default_factory=list)
    paid_amount: Money
    elapsed_seconds: int = 0


class TableBoardRow(ReadSchema):
    """One tile on the Stollar board.

    `order` is `None` for a free table. There is no `venue_tables.state` column, so
    nothing can disagree with the orders table.
    """

    table_id: int
    number: int
    seats: int
    zone_id: int | None = None
    order: OrderListItem | None = None
