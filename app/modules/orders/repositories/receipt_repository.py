from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.orders.models import Receipt


class ReceiptRepository:
    """A receipt is written once and never updated.

    There is deliberately no method that touches `payload`: a correction is a new
    order or a refund, not an edit, and the frozen payload is what makes a reprint
    two months later byte-identical regardless of what happened to the menu.
    `increment_reprint` moves the counter and nothing else.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, receipt: Receipt) -> Receipt:
        self.session.add(receipt)
        await self.session.flush()
        return receipt

    async def get_by_order(self, order_id: int) -> Receipt | None:
        result = await self.session.execute(select(Receipt).where(Receipt.order_id == order_id))
        return result.scalar_one_or_none()

    async def get_by_number(self, receipt_number: str) -> Receipt | None:
        result = await self.session.execute(
            select(Receipt).where(Receipt.receipt_number == receipt_number)
        )
        return result.scalar_one_or_none()

    async def increment_reprint(self, receipt_id: int) -> int | None:
        """Atomic bump. Returns the new count, or `None` if the receipt is gone."""
        result = await self.session.execute(
            update(Receipt)
            .where(Receipt.id == receipt_id)
            .values(reprinted_count=Receipt.reprinted_count + 1)
            .returning(Receipt.reprinted_count)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def payload_for_order(self, order_id: int) -> dict[str, Any] | None:
        receipt = await self.get_by_order(order_id)
        return receipt.payload if receipt is not None else None
