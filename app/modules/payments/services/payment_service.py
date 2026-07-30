from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import NotFoundError
from app.modules.payments.enums import PaymentStatus
from app.modules.payments.models import Payment
from app.modules.payments.repositories import PaymentRepository
from app.modules.payments.schemas import (
    BookingPaymentSummary,
    PaymentCreate,
    PaymentRead,
)

MONEY = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


class PaymentService:
    """The deposit is deducted from the total, not added to it.

    `kind` separates the deposit from the balance and both rows point at the same
    booking, so the sum of paid rows is what the guest actually handed over.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.payments = PaymentRepository(session)

    async def create_for_booking(self, user_id: int, payload: PaymentCreate) -> PaymentRead:
        payment = await self.payments.create(
            Payment(
                user_id=user_id,
                booking_id=payload.booking_id,
                subscription_id=payload.subscription_id,
                card_id=payload.card_id,
                provider=payload.provider,
                kind=payload.kind,
                amount=_money(payload.amount),
                currency=payload.currency,
                status=PaymentStatus.CREATED,
            )
        )
        await self.session.commit()
        return PaymentRead.model_validate(payment)

    async def settle_webhook(
        self, provider: str, provider_transaction_id: str, succeeded: bool, reason: str = ""
    ) -> PaymentRead:
        """Idempotent by construction.

        Providers retry webhooks. Looking the payment up by
        `(provider, provider_transaction_id)` and guarding the transition means a
        replayed callback settles nothing twice.
        """
        payment = await self.payments.get_by_provider_transaction_id(
            provider, provider_transaction_id
        )
        if payment is None:
            raise NotFoundError("No payment matches that transaction")

        if payment.status == PaymentStatus.PAID:
            return PaymentRead.model_validate(payment)

        updated = (
            await self.payments.mark_paid(payment.id, utcnow_naive())
            if succeeded
            else await self.payments.mark_failed(payment.id, reason)
        )
        await self.session.commit()
        return PaymentRead.model_validate(updated or payment)

    async def list_for_booking(self, booking_id: int) -> Sequence[PaymentRead]:
        rows = await self.payments.list_for_booking(booking_id)
        return [PaymentRead.model_validate(row) for row in rows]

    async def summary_for_booking(
        self, booking_id: int, total_amount: Decimal, currency: str = "UZS"
    ) -> BookingPaymentSummary:
        paid = await self.payments.sum_paid_for_booking(booking_id)
        return BookingPaymentSummary(
            booking_id=booking_id,
            total_amount=_money(total_amount),
            paid_amount=_money(paid),
            outstanding=_money(max(total_amount - paid, Decimal("0"))),
            currency=currency,
        )
