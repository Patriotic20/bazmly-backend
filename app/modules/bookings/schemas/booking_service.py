from pydantic import BaseModel, Field

from app.core.schemas import Money, ReadSchema


class BookingServiceCreate(BaseModel):
    venue_service_id: int
    quantity: int = Field(default=1, gt=0)


class BookingServiceRead(ReadSchema):
    id: int
    venue_service_id: int
    quantity: int
    unit_price: Money
    total_price: Money
    name_snapshot: str
