from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.promotions.models import PromoCode, PromoCodeRedemption


class PromoCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, code_id: int) -> PromoCode | None:
        result = await self.session.execute(select(PromoCode).where(PromoCode.id == code_id))
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> PromoCode | None:
        """Case-insensitive: codes are stored uppercase but typed however."""
        result = await self.session.execute(
            select(PromoCode).where(func.upper(PromoCode.code) == code.upper())
        )
        return result.scalar_one_or_none()

    async def increment_used(self, code_id: int) -> int | None:
        """Atomic `used_count = used_count + 1`.

        Never a read-modify-write: two redemptions landing together would both read
        the same count and one would be lost, silently overselling a capped code.
        """
        result = await self.session.execute(
            update(PromoCode)
            .where(PromoCode.id == code_id)
            .values(used_count=PromoCode.used_count + 1)
            .returning(PromoCode.used_count)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def count_redemptions_for_user(self, code_id: int, user_id: int) -> int:
        """Backs the per-user usage limit."""
        result = await self.session.execute(
            select(func.count())
            .select_from(PromoCodeRedemption)
            .where(
                PromoCodeRedemption.promo_code_id == code_id,
                PromoCodeRedemption.user_id == user_id,
            )
        )
        return int(result.scalar_one())

    async def record_redemption(
        self,
        code_id: int,
        user_id: int,
        discount_amount: Decimal,
        redeemed_at: datetime,
        booking_id: int | None = None,
        subscription_id: int | None = None,
    ) -> PromoCodeRedemption:
        redemption = PromoCodeRedemption(
            promo_code_id=code_id,
            user_id=user_id,
            booking_id=booking_id,
            subscription_id=subscription_id,
            discount_amount=discount_amount,
            redeemed_at=redeemed_at,
        )
        self.session.add(redemption)
        await self.session.flush()
        return redemption
