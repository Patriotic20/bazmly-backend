from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import Refund


class RefundRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, refund: Refund) -> Refund:
        self.session.add(refund)
        await self.session.flush()
        return refund

    async def get_by_id(self, refund_id: int) -> Refund | None:
        result = await self.session.execute(select(Refund).where(Refund.id == refund_id))
        return result.scalar_one_or_none()

    async def list_for_payment(self, payment_id: int) -> Sequence[Refund]:
        result = await self.session.execute(
            select(Refund)
            .where(Refund.payment_id == payment_id)
            .order_by(Refund.created_at, Refund.id)
        )
        return result.scalars().all()
