from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.modules.media.models import MediaFile


class MediaFileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, media: MediaFile) -> MediaFile:
        self.session.add(media)
        await self.session.flush()
        return media

    async def get_with_data(self, key: str) -> MediaFile | None:
        result = await self.session.execute(
            select(MediaFile).where(MediaFile.key == key).options(undefer(MediaFile.data))
        )
        return result.scalar_one_or_none()
