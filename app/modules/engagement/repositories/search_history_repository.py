from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.engagement.models import SearchHistory


class SearchHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, user_id: int, query: str, filters: dict[str, Any] | None = None
    ) -> SearchHistory:
        entry = SearchHistory(user_id=user_id, query=query, filters=filters)
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_recent(self, user_id: int, limit: int = 10) -> Sequence[SearchHistory]:
        result = await self.session.execute(
            select(SearchHistory)
            .where(SearchHistory.user_id == user_id)
            .order_by(SearchHistory.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
