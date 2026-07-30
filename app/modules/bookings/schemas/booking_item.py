from pydantic import BaseModel, Field

from app.core.schemas import Money, ReadSchema


class BookingItemCreate(BaseModel):
    menu_item_id: int
    quantity: int = Field(gt=0)


class BookingItemRead(ReadSchema):
    """`name_snapshot` and `unit_price` are frozen at confirmation.

    An old ticket must never be rebuilt by joining to live `menu_items` — prices
    and names change, and the receipt has to keep saying what was agreed.
    """

    id: int
    menu_item_id: int
    quantity: int
    unit_price: Money
    total_price: Money
    name_snapshot: str
