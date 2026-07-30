from app.core.schemas import Money, ReadSchema
from app.modules.bookings.enums import PriceLineType


class PriceLineRead(ReadSchema):
    """One row of the Detailed Price Report, frozen at confirmation."""

    id: int
    sort_order: int
    line_type: PriceLineType
    label_snapshot: str
    unit_price: Money
    quantity: int
    amount: Money
