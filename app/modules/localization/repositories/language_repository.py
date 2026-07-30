from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.localization.models import Language

DEFAULT_LANGUAGE_CODE = "uz"


class LanguageRepository:
    """Reads the three seeded UI languages."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, language_id: int) -> Language | None:
        result = await self.session.execute(select(Language).where(Language.id == language_id))
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Language | None:
        result = await self.session.execute(select(Language).where(Language.code == code))
        return result.scalar_one_or_none()

    async def get_default(self) -> Language | None:
        """Uzbek is the default; the language picker offers it first."""
        result = await self.session.execute(
            select(Language).where(Language.code == DEFAULT_LANGUAGE_CODE)
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> Sequence[Language]:
        result = await self.session.execute(
            select(Language).where(Language.is_active.is_(True)).order_by(Language.sort_order)
        )
        return result.scalars().all()
