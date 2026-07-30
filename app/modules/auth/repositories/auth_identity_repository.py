from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import AuthIdentity


class AuthIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_provider(self, provider: str, provider_user_id: str) -> AuthIdentity | None:
        result = await self.session.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == provider,
                AuthIdentity.provider_user_id == provider_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: int) -> Sequence[AuthIdentity]:
        result = await self.session.execute(
            select(AuthIdentity)
            .where(AuthIdentity.user_id == user_id)
            .order_by(AuthIdentity.provider)
        )
        return result.scalars().all()

    async def create(self, identity: AuthIdentity) -> AuthIdentity:
        self.session.add(identity)
        await self.session.flush()
        return identity

    async def delete(self, identity_id: int) -> None:
        await self.session.execute(delete(AuthIdentity).where(AuthIdentity.id == identity_id))
        await self.session.flush()
