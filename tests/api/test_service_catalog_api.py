"""`GET /v1/service-catalog` and its venue-type filter.

The filter is client-visible contract: the onboarding services screen reads this
endpoint to decide which Qo'shimcha xizmatlar to offer a branch. It used to take
`?venue_type_id=<int>` against the `venue_types` lookup table; that table is gone,
so it takes `?venue_type=<slug>` now.

The NULL leg is the one worth pinning. `applies_to_venue_type IS NULL` means "suits
any venue", so it must come back for *every* type — and because every seeded row is
NULL, a test that leaned on the seed would still pass with the type-specific leg
broken, and a refactor that dropped the `is_(None)` leg would empty the picker with
the suite green. Both legs are therefore built as fixtures here.
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.venues.enums import VenueTypeSlug
from tests.repositories import factories


async def test_a_service_that_suits_any_venue_is_returned_for_every_type(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A NULL `applies_to_venue_type` is not "no type", it is "any type"."""
    anything = await factories.make_service_catalog_entry(session, applies_to_venue_type=None)

    for slug in (VenueTypeSlug.RESTORAN, VenueTypeSlug.TOYXONA):
        response = await api_client.get(
            "/api/v1/service-catalog", params={"venue_type": slug.value}
        )

        assert response.status_code == 200, response.text
        returned = {item["id"] for item in response.json()}
        assert anything.id in returned, f"the any-venue service vanished for {slug.value}"


async def test_a_type_specific_service_is_excluded_from_the_other_type(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The restoran-only service must not reach a to'yxona's picker."""
    restoran_only = await factories.make_service_catalog_entry(
        session, applies_to_venue_type=VenueTypeSlug.RESTORAN, name="Ofitsiant xizmati"
    )
    toyxona_only = await factories.make_service_catalog_entry(
        session, applies_to_venue_type=VenueTypeSlug.TOYXONA, name="Kartej"
    )

    response = await api_client.get(
        "/api/v1/service-catalog", params={"venue_type": VenueTypeSlug.TOYXONA.value}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    returned = {item["id"] for item in body}
    assert toyxona_only.id in returned
    assert restoran_only.id not in returned

    # The slug survives the varchar column round trip rather than coming back as an id.
    by_id = {item["id"]: item for item in body}
    assert by_id[toyxona_only.id]["applies_to_venue_type"] == "toyxona"


async def test_without_a_venue_type_every_active_service_is_returned(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The filter is opt-in: no `venue_type` means no narrowing at all."""
    restoran_only = await factories.make_service_catalog_entry(
        session, applies_to_venue_type=VenueTypeSlug.RESTORAN
    )
    toyxona_only = await factories.make_service_catalog_entry(
        session, applies_to_venue_type=VenueTypeSlug.TOYXONA
    )

    response = await api_client.get("/api/v1/service-catalog")

    assert response.status_code == 200, response.text
    returned = {item["id"] for item in response.json()}
    assert {restoran_only.id, toyxona_only.id} <= returned


async def test_an_unknown_venue_type_is_rejected(api_client: AsyncClient) -> None:
    """`kafe` was folded into `restoran` when the lookup table went.

    It has to be a schema refusal rather than an unfiltered list: silently ignoring
    an unrecognised value would hand a to'yxona the restaurant-only services.
    """
    response = await api_client.get("/api/v1/service-catalog", params={"venue_type": "kafe"})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
