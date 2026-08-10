"""Creating a chain is the bootstrap: before it there is no employment row, and
without an employment row every guard in the API refuses.

These tests are about that chain of consequence, not about the payload shape. The
assertion that matters is the 200 in
`test_owner_can_edit_the_branch_they_just_created`.
"""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.staff.models import VenueStaff
from app.modules.venue_groups.models import VenueGroup
from app.modules.venues.enums import VenueTypeSlug
from app.modules.venues.models import VenueZone
from tests.api.conftest import auth_header
from tests.repositories import factories


async def group_payload(session: AsyncSession) -> dict[str, Any]:
    district = await factories.make_district(session)
    return {
        "group": {
            "primary_venue_type": VenueTypeSlug.TOYXONA.value,
            "name": "Tinchlik Plaza",
            "default_currency": "UZS",
        },
        "branch": {
            "district_id": district.id,
            "street": "Amir Temur",
            "house_number": "12A",
            "latitude": "41.311081",
            "longitude": "69.240562",
            "phone": "+998901234567",
            "name": "Chilonzor",
            "venue_type": VenueTypeSlug.TOYXONA.value,
        },
    }


async def test_creating_a_chain_writes_group_branch_and_owner_employment(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """One request, three rows. The employment row is the one nothing else can supply."""
    user = await factories.make_user(session)
    payload = await group_payload(session)

    response = await api_client.post(
        "/api/v1/venue/groups", json=payload, headers=auth_header(user.id)
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["group"]["name"] == "Tinchlik Plaza"
    assert body["group"]["owner_id"] == user.id
    assert [branch["name"] for branch in body["branches"]] == ["Chilonzor"]

    employment = (
        await session.execute(select(VenueStaff).where(VenueStaff.user_id == user.id))
    ).scalar_one()
    # NULL venue_id is the group scope — it has to carry to branches created later.
    assert employment.venue_id is None
    assert employment.role_scope == "group"
    assert employment.is_active is True


async def test_owner_can_edit_the_branch_they_just_created(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The whole point. This returned 403 for everyone before the role/permission seed."""
    user = await factories.make_user(session)
    created = await api_client.post(
        "/api/v1/venue/groups",
        json=await group_payload(session),
        headers=auth_header(user.id),
    )
    venue_id = created.json()["branches"][0]["id"]

    response = await api_client.patch(
        f"/api/v1/venue/venues/{venue_id}",
        json={"street": "Yangi ko'cha"},
        headers=auth_header(user.id),
    )

    assert response.status_code == 200, response.text
    assert response.json()["street"] == "Yangi ko'cha"


async def test_a_new_branch_is_born_with_two_zones(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Zones are rows, and a branch with none cannot filter its table board."""
    user = await factories.make_user(session)
    created = await api_client.post(
        "/api/v1/venue/groups",
        json=await group_payload(session),
        headers=auth_header(user.id),
    )
    venue_id = created.json()["branches"][0]["id"]

    zones = (
        await session.execute(select(VenueZone).where(VenueZone.venue_id == venue_id))
    ).scalars()
    assert sorted(zone.slug for zone in zones) == ["ichkari", "tashqari"]


async def test_reads_return_the_real_name(api_client: AsyncClient, session: AsyncSession) -> None:
    """`name` is a column now, not a resolved translation — the list route used to
    hand back an empty string for it."""
    user = await factories.make_user(session)
    created = await api_client.post(
        "/api/v1/venue/groups",
        json=await group_payload(session),
        headers=auth_header(user.id),
    )
    group_id = created.json()["group"]["id"]

    mine = await api_client.get("/api/v1/venue/groups/me", headers=auth_header(user.id))
    branches = await api_client.get(
        "/api/v1/venue/venues", params={"group_id": group_id}, headers=auth_header(user.id)
    )

    assert mine.json()["name"] == "Tinchlik Plaza"
    assert [row["name"] for row in branches.json()] == ["Chilonzor"]


async def test_a_second_chain_for_the_same_owner_is_409(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """`get_by_owner` is a `scalar_one_or_none`; a second chain would turn every
    later read of it into a 500."""
    user = await factories.make_user(session)
    await api_client.post(
        "/api/v1/venue/groups",
        json=await group_payload(session),
        headers=auth_header(user.id),
    )

    response = await api_client.post(
        "/api/v1/venue/groups",
        json=await group_payload(session),
        headers=auth_header(user.id),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "group_already_exists"


async def test_unknown_district_is_refused_before_anything_is_written(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A half-written chain is worse than a refused one."""
    user = await factories.make_user(session)
    payload = await group_payload(session)
    payload["branch"]["district_id"] = 10_000_000

    response = await api_client.post(
        "/api/v1/venue/groups", json=payload, headers=auth_header(user.id)
    )

    assert response.status_code == 404
    groups = (
        await session.execute(select(VenueGroup).where(VenueGroup.owner_id == user.id))
    ).scalars()
    assert list(groups) == []


async def test_owner_can_add_a_second_branch(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """`branch.create` is checked against the chain, because the branch being
    created has no id to check against."""
    user = await factories.make_user(session)
    created = await api_client.post(
        "/api/v1/venue/groups",
        json=await group_payload(session),
        headers=auth_header(user.id),
    )
    group_id = created.json()["group"]["id"]
    branch = (await group_payload(session))["branch"]
    branch["name"] = "Yunusobod"

    response = await api_client.post(
        "/api/v1/venue/venues",
        params={"group_id": group_id},
        json=branch,
        headers=auth_header(user.id),
    )

    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Yunusobod"
    assert response.json()["status"] == "draft"


async def test_a_waiter_cannot_open_a_branch(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """`branch.create` is group-scoped on purpose: opening a branch is a contract,
    not a shift decision."""
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    waiter = await factories.make_staff(session, venue, group, role_slug="waiter")

    response = await api_client.post(
        "/api/v1/venue/venues",
        params={"group_id": group.id},
        json=(await group_payload(session))["branch"],
        headers=auth_header(waiter.user_id),
    )

    assert response.status_code == 403
    assert response.json()["details"]["permission"] == "branch.create"


async def test_an_outsider_cannot_open_a_branch_in_someone_elses_chain(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Group scope is scoped to *that* group."""
    group = await factories.make_venue_group(session)
    other_group = await factories.make_venue_group(session)
    other_venue = await factories.make_venue(session, group=other_group)
    outsider = await factories.make_staff(session, other_venue, other_group, role_slug="owner")

    response = await api_client.post(
        "/api/v1/venue/venues",
        params={"group_id": group.id},
        json=(await group_payload(session))["branch"],
        headers=auth_header(outsider.user_id),
    )

    assert response.status_code == 403


async def test_adding_a_branch_without_group_id_is_422(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The guard has nothing to resolve, and says so rather than defaulting."""
    user = await factories.make_user(session)
    await api_client.post(
        "/api/v1/venue/groups",
        json=await group_payload(session),
        headers=auth_header(user.id),
    )

    response = await api_client.post(
        "/api/v1/venue/venues",
        json=(await group_payload(session))["branch"],
        headers=auth_header(user.id),
    )

    assert response.status_code == 422
