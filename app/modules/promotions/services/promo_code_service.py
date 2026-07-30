from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import PromoCodeExhaustedError, PromoCodeInvalidError
from app.modules.promotions.enums import DiscountType, PromoAppliesTo
from app.modules.promotions.repositories import PromoCodeRepository
from app.modules.promotions.schemas import PromoCodePreview

MONEY = Decimal("0.01")
PERCENT = Decimal("100")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class PromoApplication:
    """The outcome of validating a code against a specific subtotal."""

    promo_code_id: int
    code: str
    discount_amount: Decimal
    discount_type: str


class PromoCodeService:
    """Validation runs in a fixed order and stops at the first failure.

    The order matters for the message the customer sees: "this code expired" is
    more useful than "this code is fully used" when both are true, and checking
    the per-user limit before the global one would tell someone their own history
    was the problem when in fact the campaign had run out.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.promo_codes = PromoCodeRepository(session)

    async def preview(
        self,
        user_id: int,
        code: str,
        subtotal: Decimal,
        currency: str = "UZS",
        applies_to: str = PromoAppliesTo.BOOKING,
    ) -> PromoCodePreview:
        """What the discount would be. Writes nothing."""
        application = await self._validate_in_transaction(user_id, code, subtotal, applies_to)
        return PromoCodePreview(
            code=application.code,
            discount_type=DiscountType(application.discount_type),
            discount_amount=application.discount_amount,
            subtotal=subtotal,
            total_after_discount=_money(subtotal - application.discount_amount),
            currency=currency,
        )

    async def apply_in_transaction(
        self,
        user_id: int,
        code: str,
        subtotal: Decimal,
        applies_to: str = PromoAppliesTo.BOOKING,
    ) -> PromoApplication:
        """Validate and consume, without committing.

        `increment_used` is an atomic `used_count = used_count + 1` in the
        repository, never a read-modify-write: two redemptions landing together
        would otherwise both read the same count and one would be lost, quietly
        overselling a capped campaign.
        """
        application = await self._validate_in_transaction(user_id, code, subtotal, applies_to)
        await self.promo_codes.increment_used(application.promo_code_id)
        return application

    async def record_redemption_in_transaction(
        self,
        application: PromoApplication,
        user_id: int,
        booking_id: int | None = None,
        subscription_id: int | None = None,
    ) -> None:
        """Written after the booking exists, so the row points at what it paid for."""
        await self.promo_codes.record_redemption(
            code_id=application.promo_code_id,
            user_id=user_id,
            discount_amount=application.discount_amount,
            redeemed_at=utcnow_naive(),
            booking_id=booking_id,
            subscription_id=subscription_id,
        )

    async def _validate_in_transaction(
        self, user_id: int, code: str, subtotal: Decimal, applies_to: str
    ) -> PromoApplication:
        now = utcnow_naive()
        promo = await self.promo_codes.get_by_code(code)

        if promo is None:
            raise PromoCodeInvalidError("That promo code does not exist")
        if not promo.is_active:
            raise PromoCodeInvalidError("That promo code is no longer active")
        if not self._inside_window(promo.valid_from, promo.valid_to, now):
            raise PromoCodeInvalidError("That promo code is outside its valid dates")
        if not self._applies(promo.applies_to, applies_to):
            raise PromoCodeInvalidError("That promo code does not apply to this purchase")
        if promo.min_amount is not None and subtotal < promo.min_amount:
            raise PromoCodeInvalidError(
                "The order is below this code's minimum",
                details={"min_amount": str(promo.min_amount)},
            )
        if promo.usage_limit_total is not None and promo.used_count >= promo.usage_limit_total:
            raise PromoCodeExhaustedError()

        used_by_user = await self.promo_codes.count_redemptions_for_user(promo.id, user_id)
        if used_by_user >= promo.usage_limit_per_user:
            raise PromoCodeExhaustedError("You have already used this code")

        return PromoApplication(
            promo_code_id=promo.id,
            code=promo.code,
            discount_amount=self._discount_for(
                promo.discount_type, promo.value, promo.max_discount, subtotal
            ),
            discount_type=promo.discount_type,
        )

    def _inside_window(self, valid_from: datetime, valid_to: datetime, now: datetime) -> bool:
        return valid_from <= now <= valid_to

    def _applies(self, code_applies_to: str, target: str) -> bool:
        return code_applies_to in (target, PromoAppliesTo.BOTH)

    def _discount_for(
        self,
        discount_type: str,
        value: Decimal,
        max_discount: Decimal | None,
        subtotal: Decimal,
    ) -> Decimal:
        """`max_discount` is a ceiling on a percentage, not an alternative to it.

        A 50%-off code with a 100 000 ceiling gives 50% up to that amount — without
        the cap, one large booking could absorb an entire campaign budget.
        """
        if discount_type == DiscountType.PERCENT:
            discount = _money(subtotal * value / PERCENT)
        else:
            discount = _money(value)

        if max_discount is not None:
            discount = min(discount, _money(max_discount))
        return min(discount, _money(subtotal))


def sum_discounts(values: Sequence[Decimal]) -> Decimal:
    return _money(sum(values, Decimal("0")))
