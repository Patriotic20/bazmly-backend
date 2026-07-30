from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import VerificationCode


class VerificationCodeRepository:
    """Only ever stores the hash. `destination` is denormalized because at
    registration there is no user row yet."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, code: VerificationCode) -> VerificationCode:
        self.session.add(code)
        await self.session.flush()
        return code

    async def get_by_id(self, code_id: int) -> VerificationCode | None:
        result = await self.session.execute(
            select(VerificationCode).where(VerificationCode.id == code_id)
        )
        return result.scalar_one_or_none()

    async def get_active(
        self, destination: str, purpose: str, now: datetime
    ) -> VerificationCode | None:
        """Newest unconsumed, unexpired code for this destination and purpose."""
        result = await self.session.execute(
            select(VerificationCode)
            .where(
                VerificationCode.destination == destination,
                VerificationCode.purpose == purpose,
                VerificationCode.consumed_at.is_(None),
                VerificationCode.expires_at > now,
            )
            .order_by(VerificationCode.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def increment_attempts(self, code_id: int) -> int | None:
        """Atomic bump, so two parallel guesses cannot both read the same count."""
        result = await self.session.execute(
            update(VerificationCode)
            .where(VerificationCode.id == code_id)
            .values(attempts_count=VerificationCode.attempts_count + 1)
            .returning(VerificationCode.attempts_count)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def consume(self, code_id: int, now: datetime) -> VerificationCode | None:
        """Single-use: the guard makes a replayed code a no-op, not a second success."""
        result = await self.session.execute(
            update(VerificationCode)
            .where(VerificationCode.id == code_id, VerificationCode.consumed_at.is_(None))
            .values(consumed_at=now)
            .returning(VerificationCode)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def count_recent(self, destination: str, purpose: str, since: datetime) -> int:
        """Backs the resend throttle. Uses the
        `(destination, purpose, created_at)` index."""
        result = await self.session.execute(
            select(func.count())
            .select_from(VerificationCode)
            .where(
                VerificationCode.destination == destination,
                VerificationCode.purpose == purpose,
                VerificationCode.created_at >= since,
            )
        )
        return int(result.scalar_one())
