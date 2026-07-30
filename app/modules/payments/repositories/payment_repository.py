from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import Payment, PaymentStatus


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payment: Payment) -> Payment:
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get_by_id(self, payment_id: int) -> Payment | None:
        result = await self.session.execute(select(Payment).where(Payment.id == payment_id))
        return result.scalar_one_or_none()

    async def get_by_provider_transaction_id(
        self, provider: str, provider_transaction_id: str
    ) -> Payment | None:
        """The idempotency key for webhooks.

        Scoped by provider as well as id, because two providers can mint the same
        transaction reference and a cross-provider collision would settle the
        wrong payment.
        """
        result = await self.session.execute(
            select(Payment).where(
                Payment.provider == provider,
                Payment.provider_transaction_id == provider_transaction_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_booking(self, booking_id: int) -> Sequence[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.booking_id == booking_id)
            .order_by(Payment.created_at, Payment.id)
        )
        return result.scalars().all()

    async def sum_paid_for_booking(self, booking_id: int) -> Decimal:
        """Only `paid` rows count. The deposit and the balance are separate rows
        against the same booking, so this is their sum."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.booking_id == booking_id, Payment.status == PaymentStatus.PAID
            )
        )
        return Decimal(result.scalar_one())

    async def mark_paid(
        self, payment_id: int, now: datetime, provider_transaction_id: str | None = None
    ) -> Payment | None:
        values: dict[str, object] = {"status": PaymentStatus.PAID, "paid_at": now}
        if provider_transaction_id is not None:
            values["provider_transaction_id"] = provider_transaction_id
        result = await self.session.execute(
            update(Payment)
            .where(Payment.id == payment_id, Payment.status != PaymentStatus.PAID)
            .values(**values)
            .returning(Payment)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def mark_failed(self, payment_id: int, reason: str) -> Payment | None:
        result = await self.session.execute(
            update(Payment)
            .where(Payment.id == payment_id, Payment.status != PaymentStatus.PAID)
            .values(status=PaymentStatus.FAILED, failed_reason=reason)
            .returning(Payment)
        )
        await self.session.flush()
        return result.scalars().one_or_none()
