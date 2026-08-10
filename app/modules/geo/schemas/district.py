from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.schemas import ReadSchema, UpdateSchema

# Uzbekistan's bounding box, rounded outward by a degree. Narrow enough to catch a
# transposed lat/lng — the country spans 37-46 N and 55-74 E, so a swapped pair
# lands outside on both axes.
MIN_LATITUDE, MAX_LATITUDE = Decimal("36"), Decimal("46")
MIN_LONGITUDE, MAX_LONGITUDE = Decimal("55"), Decimal("74")


class DistrictCreate(BaseModel):
    region_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=100)
    latitude: Decimal = Field(ge=MIN_LATITUDE, le=MAX_LATITUDE)
    longitude: Decimal = Field(ge=MIN_LONGITUDE, le=MAX_LONGITUDE)


class DistrictUpdate(UpdateSchema):
    """Every field optional — PATCH, not PUT."""

    region_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    latitude: Decimal | None = Field(default=None, ge=MIN_LATITUDE, le=MAX_LATITUDE)
    longitude: Decimal | None = Field(default=None, ge=MIN_LONGITUDE, le=MAX_LONGITUDE)


class DistrictRead(ReadSchema):
    """Tuman va shahar bir darajada — bitta jadval, bitta sxema."""

    id: int
    region_id: int
    name: str
    latitude: Decimal
    longitude: Decimal


class RegionWithDistrictsRead(ReadSchema):
    id: int
    name: str
    code: str
    districts: list[DistrictRead]
