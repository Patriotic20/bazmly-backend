"""`has_group_permission` is what a branch-creating route asks, because there is
no `venue_id` yet to ask the branch-scoped question about."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.modules.staff.repositories import VenueStaffRepository
from tests.repositories import factories

BRANCH_CREATE = "branch.create"


async def test_group_scoped_employment_carries_across_the_chain(session: AsyncSession) -> None:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    owner = await factories.make_staff(session, venue, group, role_slug="owner")
    # The owner's real row is group-scoped; the factory pins it to a branch.
    owner.venue_id = None
    await session.flush()

    allowed = await VenueStaffRepository(session).has_group_permission(
        owner.user_id, group.id, BRANCH_CREATE
    )

    assert allowed is True


async def test_branch_scoped_employment_also_answers_the_group_question(
    session: AsyncSession,
) -> None:
    """`venue_staff.venue_group_id` is NOT NULL on every row, so a branch-scoped
    admin is still a member of the chain."""
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    admin = await factories.make_staff(session, venue, group, role_slug="admin")

    allowed = await VenueStaffRepository(session).has_group_permission(
        admin.user_id, group.id, BRANCH_CREATE
    )

    assert allowed is True


async def test_another_chain_does_not_count(session: AsyncSession) -> None:
    group = await factories.make_venue_group(session)
    other_group = await factories.make_venue_group(session)
    other_venue = await factories.make_venue(session, group=other_group)
    outsider = await factories.make_staff(session, other_venue, other_group, role_slug="owner")

    allowed = await VenueStaffRepository(session).has_group_permission(
        outsider.user_id, group.id, BRANCH_CREATE
    )

    assert allowed is False


async def test_a_role_without_the_slug_is_refused(session: AsyncSession) -> None:
    """A manager runs a branch but does not open one."""
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    manager = await factories.make_staff(session, venue, group, role_slug="manager")

    repository = VenueStaffRepository(session)

    assert await repository.has_group_permission(manager.user_id, group.id, BRANCH_CREATE) is False
    assert await repository.has_group_permission(manager.user_id, group.id, "branch.manage") is True


async def test_a_deactivated_employment_is_refused(session: AsyncSession) -> None:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    owner = await factories.make_staff(session, venue, group, role_slug="owner")

    await VenueStaffRepository(session).set_active(owner.id, False, utcnow_naive())

    allowed = await VenueStaffRepository(session).has_group_permission(
        owner.user_id, group.id, BRANCH_CREATE
    )

    assert allowed is False
