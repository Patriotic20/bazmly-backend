from datetime import datetime
from typing import Any

from app.core.schemas import ReadSchema


class ReceiptRead(ReadSchema):
    """Written once and never updated.

    `payload` freezes the printed lines so a reprint two months later is identical
    regardless of what happened to the menu. A correction is a new order or a
    refund, never an edit — which is why there is no `ReceiptUpdate`.
    """

    id: int
    order_id: int
    receipt_number: str
    printed_at: datetime
    fiscal_sign: str | None = None
    fiscal_serial: str | None = None
    payload: dict[str, Any]
    reprinted_count: int
