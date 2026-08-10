from app.modules.venues.enums import (
    VENUE_TYPE_LABELS,
    VENUE_TYPE_SORT_ORDER,
    VenueTypeSlug,
)


def test_exactly_two_venue_types() -> None:
    assert [member.value for member in VenueTypeSlug] == ["restoran", "toyxona"]


def test_every_member_has_an_uzbek_label_and_an_order() -> None:
    """The `/v1/venue-types` endpoint is gone, so these maps are the only source
    of the display name and the picker order."""
    for member in VenueTypeSlug:
        assert VENUE_TYPE_LABELS[member]
        assert VENUE_TYPE_SORT_ORDER[member] > 0

    orders = list(VENUE_TYPE_SORT_ORDER.values())
    assert len(set(orders)) == len(orders), "sort order must be a total order"


def test_restoran_sorts_before_toyxona() -> None:
    """The migration's backfill resolves a multi-typed venue by this order, so a
    change here silently changes what those venues become."""
    assert (
        VENUE_TYPE_SORT_ORDER[VenueTypeSlug.RESTORAN]
        < (VENUE_TYPE_SORT_ORDER[VenueTypeSlug.TOYXONA])
    )
