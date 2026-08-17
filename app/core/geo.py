from decimal import Decimal

from sqlalchemy import ColumnElement, Float, cast, func, literal
from sqlalchemy.orm import InstrumentedAttribute

# Mean Earth radius. Distances here are "how far is this restaurant" and "which
# tuman am I standing in", where a sphere is accurate to about 0.3% — far below
# the error already present in a hand-entered coordinate.
EARTH_RADIUS_M = 6_371_000.0


def haversine_distance_m(
    latitude: float,
    longitude: float,
    row_latitude: InstrumentedAttribute[Decimal],
    row_longitude: InstrumentedAttribute[Decimal],
) -> ColumnElement[float]:
    """Great-circle distance from a fixed point to a table's coordinates, in metres.

    The haversine formula rather than the spherical law of cosines: the latter is
    shorter but loses precision at small angles, and both callers here — "which of
    these two restaurants on the same street is nearer" and "which district centre
    is this phone closest to" — are exactly the small-angle case.

    This replaced PostGIS `ST_Distance` over a `geography` column. It costs the
    spatial index — a radius filter is now a scan — which is the trade that lets
    the schema run on any stock PostgreSQL.

    The columns are cast to float because they are `Numeric` in the schema, and
    `radians()` over numeric is exact arithmetic: correct, and far slower than the
    0.3% sphere assumption justifies.
    """
    lat1 = func.radians(literal(float(latitude)))
    lon1 = func.radians(literal(float(longitude)))
    lat2 = func.radians(cast(row_latitude, Float))
    lon2 = func.radians(cast(row_longitude, Float))

    sin_half_dlat = func.sin((lat2 - lat1) / 2)
    sin_half_dlon = func.sin((lon2 - lon1) / 2)
    chord = (
        sin_half_dlat * sin_half_dlat
        + func.cos(lat1) * func.cos(lat2) * sin_half_dlon * sin_half_dlon
    )
    return EARTH_RADIUS_M * 2 * func.asin(func.sqrt(chord))
