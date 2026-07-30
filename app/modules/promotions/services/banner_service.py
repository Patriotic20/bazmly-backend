from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.modules.promotions.enums import BannerTargetType
from app.modules.promotions.repositories import BannerRepository
from app.modules.promotions.schemas import BannerRead


class BannerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.banners = BannerRepository(session)

    async def list_active(self, language_id: int) -> Sequence[BannerRead]:
        rows = await self.banners.list_active(language_id, utcnow_naive())
        return [
            BannerRead(
                id=row.banner.id,
                image_url=row.banner.image_url,
                title=row.title,
                subtitle=row.subtitle,
                target_type=BannerTargetType(row.banner.target_type),
                target_id=row.banner.target_id,
                target_url=row.banner.target_url,
                sort_order=row.banner.sort_order,
                starts_at=row.banner.starts_at,
                ends_at=row.banner.ends_at,
            )
            for row in rows
        ]
