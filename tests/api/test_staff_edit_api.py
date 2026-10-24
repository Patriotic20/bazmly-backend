"""Editing an employee from the staff list, and the photos of a branch."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import UserRole
from app.modules.staff.models import VenueStaff
from app.modules.venue_groups.models import VenueGroup
from app.modules.venues.models import Venue
from tests.api.conftest import auth_header
from tests.repositories import factories

STAFF_MANAGE = "staff.manage"
BRANCH_MANAGE = "branch.manage"


async def manager_and_waiter(session: AsyncSession) -> tuple[VenueStaff, VenueStaff]:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    manager = await factories.make_staff(session, venue, group, role_slug="manager")
    waiter = await factories.make_staff(session, venue, group, role_slug="waiter")
    await factories.grant(session, "manager", STAFF_MANAGE)
    return manager, waiter


async def test_manager_renames_and_promotes_an_employee(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    manager, waiter = await manager_and_waiter(session)
    cook = await factories.get_staff_role(session, "cook")

    response = await api_client.patch(
        f"/api/v1/venue/staff/{waiter.id}",
        params={"venue_id": waiter.venue_id},
        json={"first_name": "Aziz", "last_name": "Karimov", "staff_role_id": cook.id},
        headers=auth_header(manager.user_id),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["first_name"] == "Aziz"
    assert body["user"]["last_name"] == "Karimov"
    assert body["staff_role_id"] == cook.id
    assert body["role_name"] == cook.name


async def test_a_new_password_replaces_the_old_one(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    manager, waiter = await manager_and_waiter(session)

    response = await api_client.post(
        f"/api/v1/venue/staff/{waiter.id}/password",
        params={"venue_id": waiter.venue_id},
        headers=auth_header(manager.user_id),
    )

    assert response.status_code == 200, response.text
    issued = response.json()
    login = await api_client.post(
        "/api/v1/auth/staff-login",
        json={"login": issued["login"], "password": issued["temporary_password"]},
    )
    assert login.status_code == 200, login.text


async def test_a_person_with_their_own_account_keeps_their_name_and_password(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A customer hired with their existing account is not the owner's to reset."""
    manager, waiter = await manager_and_waiter(session)
    customer = await factories.make_user(session, role=UserRole.CUSTOMER)
    waiter.user_id = customer.id
    await session.flush()

    rename = await api_client.patch(
        f"/api/v1/venue/staff/{waiter.id}",
        params={"venue_id": waiter.venue_id},
        json={"first_name": "Boshqa"},
        headers=auth_header(manager.user_id),
    )
    reset = await api_client.post(
        f"/api/v1/venue/staff/{waiter.id}/password",
        params={"venue_id": waiter.venue_id},
        headers=auth_header(manager.user_id),
    )

    assert rename.status_code == 422
    assert reset.status_code == 422


async def test_an_employee_of_another_chain_cannot_be_edited(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The guard reads the query's branch; the row must belong to a chain the
    caller manages too, or any id would do."""
    manager, _waiter = await manager_and_waiter(session)
    _other_manager, stranger = await manager_and_waiter(session)

    response = await api_client.patch(
        f"/api/v1/venue/staff/{stranger.id}",
        params={"venue_id": manager.venue_id},
        json={"first_name": "Buzildi"},
        headers=auth_header(manager.user_id),
    )

    assert response.status_code == 403


async def test_the_owner_cannot_be_edited(api_client: AsyncClient, session: AsyncSession) -> None:
    manager, _waiter = await manager_and_waiter(session)
    group = await session.get(VenueGroup, manager.venue_group_id)
    assert group is not None
    venue = await session.get(Venue, manager.venue_id)
    assert venue is not None
    owner = await factories.make_staff(session, venue, group, role_slug="owner")

    response = await api_client.patch(
        f"/api/v1/venue/staff/{owner.id}/active",
        params={"venue_id": manager.venue_id, "is_active": False},
        headers=auth_header(manager.user_id),
    )

    assert response.status_code == 403


async def test_branch_photos_are_replaced_whole_and_the_first_is_the_cover(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    manager = await factories.make_staff(session, venue, group, role_slug="manager")
    await factories.grant(session, "manager", BRANCH_MANAGE)
    path = f"/api/v1/venue/venues/{venue.id}/photos"

    first = await api_client.put(
        path,
        json={"urls": ["https://x.test/1.jpg", "https://x.test/2.jpg"]},
        headers=auth_header(manager.user_id),
    )
    second = await api_client.put(
        path, json={"urls": ["https://x.test/3.jpg"]}, headers=auth_header(manager.user_id)
    )
    too_many = await api_client.put(
        path,
        json={"urls": [f"https://x.test/{n}.jpg" for n in range(6)]},
        headers=auth_header(manager.user_id),
    )

    assert first.status_code == 200, first.text
    assert [p["is_cover"] for p in first.json()] == [True, False]
    assert second.status_code == 200
    assert [p["url"] for p in second.json()] == ["https://x.test/3.jpg"]
    assert too_many.status_code == 422
