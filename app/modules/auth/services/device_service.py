from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.modules.auth.repositories import DeviceRepository
from app.modules.auth.schemas import DeviceCreate, DeviceRead


class DeviceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.devices = DeviceRepository(session)

    async def register(self, user_id: int, payload: DeviceCreate) -> DeviceRead:
        """Re-installing with the same uuid updates the push token in place rather
        than orphaning the old row and silently doubling every notification."""
        device = await self.devices.upsert(
            user_id=user_id,
            device_uuid=payload.device_uuid,
            platform=payload.platform,
            app_version=payload.app_version,
            now=utcnow_naive(),
            push_token=payload.push_token,
        )
        await self.session.commit()
        return DeviceRead.model_validate(device)

    async def list_for_user(self, user_id: int) -> Sequence[DeviceRead]:
        devices = await self.devices.list_for_user(user_id)
        return [DeviceRead.model_validate(device) for device in devices]
