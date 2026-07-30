from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.promotions.models import UserPromoCode, UserPromoCodeStatus


class UserPromoCodeRepository:
    """The Voucher tab. The countdown on each card is `expires_at - now()`
    computed at render — never stored."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_promo_code_id: int) -> UserPromoCode | None:
        result = await self.session.execute(
            select(UserPromoCode).where(UserPromoCode.id == user_promo_code_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: int, status: str = UserPromoCodeStatus.ACTIVE
    ) -> Sequence[UserPromoCode]:
        """Soonest to expire first — uses the
        `(user_id, status, expires_at)` index."""
        result = await self.session.execute(
            select(UserPromoCode)
            .where(UserPromoCode.user_id == user_id, UserPromoCode.status == status)
            .order_by(UserPromoCode.expires_at)
        )
        return result.scalars().all()

    async def mark_used(self, user_promo_code_id: int, now: datetime) -> UserPromoCode | None:
        """Guarded, so a voucher cannot be spent twice by two parallel checkouts."""
        result = await self.session.execute(
            update(UserPromoCode)
            .where(
                UserPromoCode.id == user_promo_code_id,
                UserPromoCode.status == UserPromoCodeStatus.ACTIVE,
            )
            .values(status=UserPromoCodeStatus.USED, used_at=now)
            .returning(UserPromoCode)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def expire_stale(self, now: datetime) -> Sequence[int]:
        result = await self.session.execute(
            update(UserPromoCode)
            .where(
                UserPromoCode.status == UserPromoCodeStatus.ACTIVE,
                UserPromoCode.expires_at <= now,
            )
            .values(status=UserPromoCodeStatus.EXPIRED)
            .returning(UserPromoCode.id)
        )
        await self.session.flush()
        return list(result.scalars().all())

    async def create(self, user_promo_code: UserPromoCode) -> UserPromoCode:
        self.session.add(user_promo_code)
        await self.session.flush()
        return user_promo_code
