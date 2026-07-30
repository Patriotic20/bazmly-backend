from datetime import time
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import ReadSchema


class WorkingHoursCreate(BaseModel):
    weekday: int = Field(ge=0, le=6)
    opens_at: time | None = None
    closes_at: time | None = None
    is_closed: bool = False

    @model_validator(mode="after")
    def _open_days_need_hours(self) -> Self:
        if not self.is_closed and (self.opens_at is None or self.closes_at is None):
            raise ValueError("An open day needs both opens_at and closes_at")
        return self


class WorkingHoursReplace(BaseModel):
    """Butun hafta bir yo'la yoziladi.

    Tahrirlash yettala qatorni qayta yozadi, kunlarni taqqoslamaydi — shunda
    olib tashlangan kun eski qator bo'lib qolmaydi.
    """

    days: list[WorkingHoursCreate] = Field(min_length=1, max_length=7)


class WorkingHoursRead(ReadSchema):
    weekday: int
    opens_at: time | None = None
    closes_at: time | None = None
    is_closed: bool
