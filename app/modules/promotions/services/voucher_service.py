from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import NotFoundError
from app.modules.promotions.enums import UserPromoCodeStatus
from app.modules.promotions.repositories import UserPromoCodeRepository
from app.modules.promotions.schemas import UserPromoCodeRead


class VoucherService:
    """The Voucher tab."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.vouchers = UserPromoCodeRepository(session)

    async def list_for_user(
        self, user_id: int, status: str = UserPromoCodeStatus.ACTIVE
    ) -> Sequence[UserPromoCodeRead]:
        """`seconds_remaining` is computed here at read.

        Storing the countdown would mean storing a number that is wrong one second
        after it is written.
        """
        now = utcnow_naive()
        rows = await self.vouchers.list_for_user(user_id, status)
        result: list[UserPromoCodeRead] = []
        for row in rows:
            read = UserPromoCodeRead.model_validate(row)
            remaining = int((row.expires_at - now).total_seconds())
            result.append(read.model_copy(update={"seconds_remaining": max(remaining, 0)}))
        return result

    async def mark_used(self, user_promo_code_id: int) -> UserPromoCodeRead:
        updated = await self.vouchers.mark_used(user_promo_code_id, utcnow_naive())
        if updated is None:
            raise NotFoundError("That voucher is not available")
        await self.session.commit()
        return UserPromoCodeRead.model_validate(updated)

    async def expire_stale(self) -> Sequence[int]:
        ids = await self.vouchers.expire_stale(utcnow_naive())
        await self.session.commit()
        return ids
