from datetime import datetime

from pydantic import BaseModel, Field

from app.core.schemas import ReadSchema
from app.modules.auth.enums import DevicePlatform


class DeviceCreate(BaseModel):
    device_uuid: str = Field(min_length=1, max_length=255)
    platform: DevicePlatform
    app_version: str = Field(min_length=1, max_length=20)
    push_token: str | None = None


class DeviceRead(ReadSchema):
    """Qurilma ma'lumoti. `push_token` ro'yxatlarda qaytarilmaydi."""

    id: int
    device_uuid: str
    platform: DevicePlatform
    app_version: str
    last_seen_at: datetime
