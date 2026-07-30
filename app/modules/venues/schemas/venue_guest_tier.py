from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import Money, ReadSchema


class VenueGuestTierCreate(BaseModel):
    min_guests: int = Field(gt=0)
    max_guests: int | None = Field(default=None, gt=0)
    base_price: Money
    sort_order: int = 0

    @model_validator(mode="after")
    def _range_is_ordered(self) -> Self:
        if self.max_guests is not None and self.max_guests < self.min_guests:
            raise ValueError("max_guests must not be below min_guests")
        return self


class VenueGuestTierRead(ReadSchema):
    """To'yxona bands. A null `max_guests` is the open-ended top band ("300+")."""

    id: int
    min_guests: int
    max_guests: int | None = None
    base_price: Money
    sort_order: int
