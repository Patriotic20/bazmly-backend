"""Pricing a to'yxona's extra services from the panel, and who may do it."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.staff.models import VenueStaff
from app.modules.venue_groups.models import VenueGroup
from app.modules.venues.models import Venue
from tests.api.conftest import auth_header
from tests.repositories import factories

SETTINGS_EDIT = "settings.edit"


async def branch_with_manager(session: AsyncSession) -> tuple[VenueGroup, Venue, VenueStaff]:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    manager = await factories.make_staff(session, venue, group, role_slug="manager")
    await factories.grant(session, "manager", SETTINGS_EDIT)
    return group, venue, manager


async def test_a_service_is_priced_edited_and_removed(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    group, venue, manager = await branch_with_manager(session)
    catalog = await factories.make_service_catalog_entry(session, name="Dasturxon (Premium)")
    headers = auth_header(manager.user_id)

    created = await api_client.post(
        "/api/v1/venue/services",
        params={"venue_id": venue.id, "group_id": group.id},
        json={
            "service_catalog_id": catalog.id,
            "price": "14000000",
            "items": [{"name": "Osh", "price": "60000"}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Dasturxon (Premium)"
    service_id = created.json()["id"]

    edited = await api_client.patch(
        f"/api/v1/venue/services/{service_id}",
        params={"venue_id": venue.id},
        json={"price": "16000000", "items": [{"name": "Somsa", "price": "15000"}]},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    assert float(edited.json()["price"]) == 16000000
    assert [item["name"] for item in edited.json()["items"]] == ["Somsa"]

    removed = await api_client.delete(
        f"/api/v1/venue/services/{service_id}",
        params={"venue_id": venue.id},
        headers=headers,
    )
    assert removed.status_code == 204
    listed = await api_client.get(
        f"/api/v1/venues/{venue.id}/services", params={"group_id": group.id}
    )
    assert service_id not in {s["id"] for s in listed.json()}


async def test_another_chains_service_cannot_be_edited(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    _group, venue, manager = await branch_with_manager(session)
    other_group, other_venue, other_manager = await branch_with_manager(session)
    catalog = await factories.make_service_catalog_entry(session)

    theirs = await api_client.post(
        "/api/v1/venue/services",
        params={"venue_id": other_venue.id, "group_id": other_group.id},
        json={"service_catalog_id": catalog.id, "price": "1000000"},
        headers=auth_header(other_manager.user_id),
    )
    assert theirs.status_code == 201, theirs.text

    response = await api_client.patch(
        f"/api/v1/venue/services/{theirs.json()['id']}",
        params={"venue_id": venue.id},
        json={"price": "1"},
        headers=auth_header(manager.user_id),
    )

    assert response.status_code == 404


async def test_a_service_cannot_be_written_into_another_chain(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The guard proves the branch; `group_id` must be that branch's own chain."""
    _group, venue, manager = await branch_with_manager(session)
    other_group, _other_venue, _other_manager = await branch_with_manager(session)
    catalog = await factories.make_service_catalog_entry(session)

    response = await api_client.post(
        "/api/v1/venue/services",
        params={"venue_id": venue.id, "group_id": other_group.id},
        json={"service_catalog_id": catalog.id, "price": "1000000"},
        headers=auth_header(manager.user_id),
    )

    assert response.status_code == 403
