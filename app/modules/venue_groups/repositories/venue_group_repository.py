from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.venue_groups.models import VenueGroup
from app.modules.venues.models import Venue


@dataclass(frozen=True, slots=True)
class BranchRow:
    venue: Venue
    name: str
    tagline: str | None


@dataclass(frozen=True, slots=True)
class VenueGroupWithBranches:
    group: VenueGroup
    name: str
    branches: Sequence[BranchRow]


class VenueGroupRepository:
    """The chain. Onboarding writes the group and its first branch together —
    a nullable `venue_group_id` would mean two code paths forever."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, group_id: int) -> VenueGroup | None:
        result = await self.session.execute(select(VenueGroup).where(VenueGroup.id == group_id))
        return result.scalar_one_or_none()

    async def get_by_owner(self, owner_id: int) -> VenueGroup | None:
        result = await self.session.execute(
            select(VenueGroup).where(VenueGroup.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def get_with_branches(self, group_id: int) -> VenueGroupWithBranches | None:
        head = await self.session.execute(
            select(VenueGroup, VenueGroup.name).where(VenueGroup.id == group_id)
        )
        row = head.one_or_none()
        if row is None:
            return None
        branches = await self.session.execute(
            select(Venue, Venue.name, Venue.tagline)
            .where(Venue.venue_group_id == group_id)
            .order_by(Venue.id)
        )
        return VenueGroupWithBranches(
            group=row[0],
            name=row[1] or "",
            branches=[BranchRow(venue=b[0], name=b[1] or "", tagline=b[2]) for b in branches.all()],
        )

    async def create_with_first_branch(
        self, group: VenueGroup, venue: Venue
    ) -> tuple[VenueGroup, Venue]:
        """Group and first branch in one flush.

        Two flushes are needed only because `venue.venue_group_id` is NOT NULL and
        the group's id is server-generated; both land in the caller's single
        transaction, so nothing is visible until the service commits.
        """
        self.session.add(group)
        await self.session.flush()

        venue.venue_group_id = group.id
        self.session.add(venue)
        await self.session.flush()
        return group, venue

    async def update_fields(self, group_id: int, values: dict[str, Any]) -> VenueGroup | None:
        if not values:
            return await self.get_by_id(group_id)
        result = await self.session.execute(
            update(VenueGroup)
            .where(VenueGroup.id == group_id)
            .values(**values)
            .returning(VenueGroup)
        )
        await self.session.flush()
        return result.scalars().one_or_none()
