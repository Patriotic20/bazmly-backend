"""The staff reads take a required `group_id`, but it is a claim, not authority.

`VerifiedGroupId` checks the caller actually works in the chain they name —
without it, any signed-in user could read another chain's staff list by picking
its id off a URL.
"""

from datetime import time

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import auth_header
from tests.repositories import factories


async def make_chain(session: AsyncSession):
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    await factories.make_working_hours(session, venue, time(8, 0), time(22, 0))
    return group, venue


async def test_own_group_is_readable(api_client: AsyncClient, session: AsyncSession) -> None:
    group, venue = await make_chain(session)
    member = await factories.make_staff(session, venue, group)

    response = await api_client.get(
        "/api/v1/venue/staff",
        params={"group_id": group.id},
        headers=auth_header(member.user_id),
    )

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [member.id]


async def test_a_foreign_group_is_refused(api_client: AsyncClient, session: AsyncSession) -> None:
    group, venue = await make_chain(session)
    member = await factories.make_staff(session, venue, group)
    other_group, _ = await make_chain(session)

    for path in ("/api/v1/venue/staff", "/api/v1/venue/staff/counts"):
        response = await api_client.get(
            path,
            params={"group_id": other_group.id},
            headers=auth_header(member.user_id),
        )
        assert response.status_code == 403, path
