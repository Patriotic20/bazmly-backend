from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.schemas import ReadSchema


class UserAddressCreate(BaseModel):
    district_id: int
    label: str = Field(min_length=1, max_length=255)
    latitude: Decimal
    longitude: Decimal


class UserAddressRead(ReadSchema):
    """Backs "Oxirgi manzillar"."""

    id: int
    district_id: int
    label: str
    latitude: Decimal
    longitude: Decimal
    last_used_at: datetime
