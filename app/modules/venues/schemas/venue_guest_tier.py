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
            raise ValueError("`max_guests` `min_guests` dan kichik bo'lmasligi kerak")
        return self


class VenueGuestTierRead(ReadSchema):
    """To'yxona narx bosqichlari. `max_guests` bo'sh bo'lsa — bu ochiq yuqori bosqich."""

    id: int
    min_guests: int
    max_guests: int | None = None
    base_price: Money
    sort_order: int
