from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.venue_groups.repositories import VenueGroupRepository
from app.modules.venue_groups.schemas import (
    BranchListItem,
    VenueGroupRead,
    VenueGroupUpdate,
    VenueGroupWithBranchesRead,
)


class VenueGroupService:
    """The chain. Every venue belongs to one, including a single restaurant."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.groups = VenueGroupRepository(session)

    async def get_for_owner(self, owner_id: int) -> VenueGroupRead:
        group = await self.groups.get_by_owner(owner_id)
        if group is None:
            raise NotFoundError("Sizda hali tarmoq yo'q")
        return VenueGroupRead.model_validate(group)

    async def get_with_branches(self, group_id: int) -> VenueGroupWithBranchesRead:
        result = await self.groups.get_with_branches(group_id)
        if result is None:
            raise NotFoundError("Tarmoq topilmadi")
        return VenueGroupWithBranchesRead(
            group=VenueGroupRead.model_validate(result.group),
            branches=[
                BranchListItem(
                    id=branch.venue.id,
                    name=branch.name,
                    tagline=branch.tagline,
                    status=branch.venue.status,
                )
                for branch in result.branches
            ],
        )

    async def update_details(self, group_id: int, payload: VenueGroupUpdate) -> VenueGroupRead:
        updated = await self.groups.update_fields(group_id, payload.model_dump(exclude_unset=True))
        if updated is None:
            raise NotFoundError("Tarmoq topilmadi")
        await self.session.commit()
        return VenueGroupRead.model_validate(updated)
