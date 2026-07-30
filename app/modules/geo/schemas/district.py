from decimal import Decimal

from app.core.schemas import ReadSchema


class DistrictRead(ReadSchema):
    """Holds both tuman and shahar rows — one level, one table, one schema."""

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
