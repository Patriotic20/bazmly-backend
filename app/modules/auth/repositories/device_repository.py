from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import Device


class DeviceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, device_id: int) -> Device | None:
        result = await self.session.execute(select(Device).where(Device.id == device_id))
        return result.scalar_one_or_none()

    async def get_by_uuid(self, user_id: int, device_uuid: str) -> Device | None:
        result = await self.session.execute(
            select(Device).where(Device.user_id == user_id, Device.device_uuid == device_uuid)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: int,
        device_uuid: str,
        platform: str,
        app_version: str,
        now: datetime,
        push_token: str | None = None,
    ) -> Device:
        """Matches the `UNIQUE (user_id, device_uuid)` pair. Re-installing the app
        with the same uuid updates the push token rather than orphaning the old row.
        """
        existing = await self.get_by_uuid(user_id, device_uuid)
        if existing is not None:
            existing.platform = platform
            existing.app_version = app_version
            existing.last_seen_at = now
            if push_token is not None:
                existing.push_token = push_token
            await self.session.flush()
            return existing

        device = Device(
            user_id=user_id,
            device_uuid=device_uuid,
            platform=platform,
            app_version=app_version,
            push_token=push_token,
            last_seen_at=now,
        )
        self.session.add(device)
        await self.session.flush()
        return device

    async def list_for_user(self, user_id: int) -> Sequence[Device]:
        result = await self.session.execute(
            select(Device).where(Device.user_id == user_id).order_by(Device.last_seen_at.desc())
        )
        return result.scalars().all()

    async def list_push_tokens_for_user(self, user_id: int) -> Sequence[str]:
        result = await self.session.execute(
            select(Device.push_token)
            .where(Device.user_id == user_id, Device.push_token.is_not(None))
            .order_by(Device.last_seen_at.desc())
        )
        return [token for token in result.scalars().all() if token is not None]
