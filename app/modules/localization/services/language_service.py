# TODO(service): added by the API task — localization had no service, but both
# `GET /v1/languages` and the `get_language_id` dependency need one. Recorded in
# DECISIONS.md.
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.localization.repositories import LanguageRepository
from app.modules.localization.schemas import LanguageRead


class LanguageService:
    """The three seeded UI languages. Read-only — the list is platform-owned."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.languages = LanguageRepository(session)

    async def list_active(self) -> Sequence[LanguageRead]:
        rows = await self.languages.list_active()
        return [LanguageRead.model_validate(row) for row in rows]

    async def get_by_code(self, code: str) -> LanguageRead | None:
        """Used by the `Accept-Language` resolution chain, so an unknown tag is a
        `None` to fall through on rather than an error."""
        language = await self.languages.get_by_code(code)
        return LanguageRead.model_validate(language) if language is not None else None
