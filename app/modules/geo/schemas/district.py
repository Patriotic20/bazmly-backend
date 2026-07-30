from decimal import Decimal

from app.core.schemas import ReadSchema


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
