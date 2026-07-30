from pydantic import BaseModel, Field, field_validator

from app.core.schemas import ReadSchema


class VenueTableCreate(BaseModel):
    number: int = Field(gt=0)
    seats: int = Field(gt=0)
    zone_id: int | None = None


class TableCountsCreate(BaseModel):
    """Onboarding's capacity buckets: `{2: 4, 4: 6, 8: 2}`.

    Input, not state — the service expands these into numbered rows and the
    buckets themselves are never stored.
    """

    counts: dict[int, int] = Field(min_length=1)
    zone_id: int | None = None

    @field_validator("counts")
    @classmethod
    def _positive(cls, value: dict[int, int]) -> dict[int, int]:
        for seats, count in value.items():
            if seats <= 0 or count <= 0:
                raise ValueError("Seat count and table count must both be positive")
        return value


class VenueTableRead(ReadSchema):
    id: int
    number: int
    seats: int
    zone_id: int | None = None
    is_active: bool
