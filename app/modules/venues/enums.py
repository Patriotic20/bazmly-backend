"""Enum values for the `venues` module.

Re-exported from the model files that declare them, so models and schemas
share one object per enum. Schemas import from here; nothing redeclares an
enum. See DECISIONS.md for why the declarations still sit in the models.

`VenueTypeSlug` replaced a `venue_types` lookup table and a `venue_venue_types`
join. Two values that never change do not need a table, and the endpoint that
served them is gone — so the label and the order live here, next to the values
they describe, instead of in a row the client has to fetch first.
"""

from enum import StrEnum

from app.modules.venues.models.venue import VenueStatus


class VenueTypeSlug(StrEnum):
    RESTORAN = "restoran"
    TOYXONA = "toyxona"


VENUE_TYPE_LABELS: dict[VenueTypeSlug, str] = {
    VenueTypeSlug.RESTORAN: "Restoran",
    VenueTypeSlug.TOYXONA: "To'yxona",
}

VENUE_TYPE_SORT_ORDER: dict[VenueTypeSlug, int] = {
    VenueTypeSlug.RESTORAN: 1,
    VenueTypeSlug.TOYXONA: 2,
}

__all__ = [
    "VENUE_TYPE_LABELS",
    "VENUE_TYPE_SORT_ORDER",
    "VenueStatus",
    "VenueTypeSlug",
]
