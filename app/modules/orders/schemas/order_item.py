from datetime import datetime

from pydantic import BaseModel, Field

from app.core.schemas import Money, ReadSchema, UpdateSchema
from app.modules.orders.enums import OrderItemStatus


class OrderItemCreate(BaseModel):
    menu_item_id: int
    variant_id: int | None = None
    quantity: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=500)


class OrderItemUpdate(UpdateSchema):
    quantity: int | None = Field(default=None, gt=0)
    status: OrderItemStatus | None = None
    note: str | None = Field(default=None, max_length=500)


class OrderItemRead(ReadSchema):
    """Item-level status exists because Oshpaz is a role: the kitchen queue is a
    per-dish question, not a per-check one."""

    id: int
    menu_item_id: int
    variant_id: int | None = None
    quantity: int
    unit_price: Money
    discount_amount: Money
    total_price: Money
    name_snapshot: str
    variant_name_snapshot: str | None = None
    status: OrderItemStatus
    note: str | None = None
    added_at: datetime
    served_at: datetime | None = None


class KitchenQueueItem(ReadSchema):
    """Oshpaz's queue, oldest first, with the table to call out."""

    id: int
    order_id: int
    table_number: int | None = None
    name_snapshot: str
    variant_name_snapshot: str | None = None
    quantity: int
    status: OrderItemStatus
    note: str | None = None
    added_at: datetime
