from pydantic import BaseModel, Field

from app.core.schemas import ReadSchema, UpdateSchema


class RegionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=2, max_length=20, pattern=r"^UZ-[A-Z]{2}$")


class RegionUpdate(UpdateSchema):
    """Every field optional — PATCH, not PUT."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    code: str | None = Field(default=None, min_length=2, max_length=20, pattern=r"^UZ-[A-Z]{2}$")


class RegionRead(ReadSchema):
    id: int
    name: str
    code: str
