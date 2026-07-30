from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import NotFoundError, ReceiptAlreadyIssuedError
from app.core.security import generate_token
from app.modules.orders.models import Receipt
from app.modules.orders.repositories import OrderRepository, ReceiptRepository
from app.modules.orders.schemas import ReceiptRead


class ReceiptService:
    """A receipt is written once and never updated.

    A correction is a new order or a refund, never an edit, and `payload` freezes
    the printed lines so a reprint two months later is identical regardless of what
    happened to the menu since.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.receipts = ReceiptRepository(session)
        self.orders = OrderRepository(session)

    async def issue_in_transaction(
        self, order_id: int, staff_id: int, payload: dict[str, Any]
    ) -> Receipt:
        """Called by `OrderService.close` inside its unit of work.

        Guards on the existing row rather than relying on the unique index, so a
        second close is a domain error naming the rule instead of an integrity
        error naming a constraint.
        """
        existing = await self.receipts.get_by_order(order_id)
        if existing is not None:
            raise ReceiptAlreadyIssuedError(
                "This order already has a receipt",
                details={"receipt_number": existing.receipt_number},
            )

        return await self.receipts.create(
            Receipt(
                order_id=order_id,
                receipt_number=generate_token(8),
                printed_at=utcnow_naive(),
                printed_by_staff_id=staff_id,
                payload=payload,
                reprinted_count=0,
            )
        )

    async def get_for_order(self, order_id: int) -> ReceiptRead:
        receipt = await self.receipts.get_by_order(order_id)
        if receipt is None:
            raise NotFoundError("No receipt has been issued for this order")
        return ReceiptRead.model_validate(receipt)

    async def reprint(self, order_id: int) -> ReceiptRead:
        """Increments the counter and changes nothing else."""
        receipt = await self.receipts.get_by_order(order_id)
        if receipt is None:
            raise NotFoundError("No receipt has been issued for this order")
        await self.receipts.increment_reprint(receipt.id)
        await self.session.commit()
        refreshed = await self.receipts.get_by_order(order_id)
        if refreshed is None:
            raise NotFoundError("No receipt has been issued for this order")
        return ReceiptRead.model_validate(refreshed)
