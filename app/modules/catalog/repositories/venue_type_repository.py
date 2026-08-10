from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import VenueType


class VenueTypeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, venue_type_id: int) -> VenueType | None:
        result = await self.session.execute(select(VenueType).where(VenueType.id == venue_type_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> VenueType | None:
        result = await self.session.execute(select(VenueType).where(VenueType.slug == slug))
        return result.scalar_one_or_none()

    async def list_active(self) -> Sequence[VenueType]:
        result = await self.session.execute(
            select(VenueType).where(VenueType.is_active.is_(True)).order_by(VenueType.sort_order)
        )
        return list(result.scalars().all())
