"""Authority comes from `venue_staff`, never from a claim in the token."""

from datetime import time

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.staff.models import Permission, StaffRole, StaffRolePermission
from app.modules.venue_groups.models import VenueGroup
from app.modules.venues.models import Venue
from tests.api.conftest import auth_header
from tests.repositories import factories

BRANCH_MANAGE = "branch.manage"


async def grant(session: AsyncSession, role_slug: str, *slugs: str) -> None:
    role = (
        await session.execute(select(StaffRole).where(StaffRole.slug == role_slug))
    ).scalar_one()
    for slug in slugs:
        permission = (
            await session.execute(select(Permission).where(Permission.slug == slug))
        ).scalar_one()
        session.add(StaffRolePermission(staff_role_id=role.id, permission_id=permission.id))
    await session.flush()


async def make_branch(
    session: AsyncSession, group: VenueGroup | None = None
) -> tuple[VenueGroup, Venue]:
    group = group or await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    await factories.make_working_hours(session, venue, time(8, 0), time(22, 0))
    return group, venue


async def test_waiter_cannot_edit_a_branch(api_client: AsyncClient, session: AsyncSession) -> None:
    """A waiter has no branch.manage, so the guard refuses before the service runs."""
    group, venue = await make_branch(session)
    waiter = await factories.make_staff(session, venue, group, role_slug="waiter")
    await grant(session, "manager", BRANCH_MANAGE)

    response = await api_client.patch(
        f"/api/v1/venue/venues/{venue.id}",
        json={"street": "Yangi ko'cha"},
        headers=auth_header(waiter.user_id),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    assert response.json()["details"]["permission"] == BRANCH_MANAGE


async def test_owner_of_another_group_cannot_edit_this_branch(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Group scope is scoped to *that* group — it is not a global bypass."""
    _group, venue = await make_branch(session)

    other_group = await factories.make_venue_group(session)
    other_venue = await factories.make_venue(session, group=other_group)
    outsider = await factories.make_staff(session, other_venue, other_group, role_slug="owner")
    await grant(session, "owner", BRANCH_MANAGE)

    response = await api_client.patch(
        f"/api/v1/venue/venues/{venue.id}",
        json={"street": "Yangi ko'cha"},
        headers=auth_header(outsider.user_id),
    )

    assert response.status_code == 403


async def test_group_admin_may_edit_any_branch_in_the_group(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A group-scoped row has `venue_id IS NULL` and satisfies a venue-scoped check
    at every branch in its chain — the OR in `has_permission`."""
    group, first_branch = await make_branch(session)
    second_branch = await factories.make_venue(session, group=group)
    await grant(session, "admin", BRANCH_MANAGE)

    admin_user = await factories.make_user(session)
    admin_role = (
        await session.execute(select(StaffRole).where(StaffRole.slug == "admin"))
    ).scalar_one()
    from datetime import UTC, datetime

    from app.modules.staff.models import VenueStaff

    session.add(
        VenueStaff(
            venue_group_id=group.id,
            venue_id=None,  # group scope
            user_id=admin_user.id,
            staff_role_id=admin_role.id,
            role_scope=admin_role.scope,
            is_active=True,
            invited_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    await session.flush()

    for branch in (first_branch, second_branch):
        response = await api_client.patch(
            f"/api/v1/venue/venues/{branch.id}",
            json={"street": "Amir Temur 12"},
            headers=auth_header(admin_user.id),
        )
        assert response.status_code == 200, response.text


async def test_unauthenticated_staff_write_is_refused(api_client: AsyncClient) -> None:
    response = await api_client.patch("/api/v1/venue/venues/1", json={"street": "X"})

    assert response.status_code == 403
