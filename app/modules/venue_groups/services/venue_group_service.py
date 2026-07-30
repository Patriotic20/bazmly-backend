from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.venue_groups.models import VenueGroup
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
        return _group_read(group)

    async def get_with_branches(
        self, group_id: int, language_id: int
    ) -> VenueGroupWithBranchesRead:
        result = await self.groups.get_with_branches(group_id, language_id)
        if result is None:
            raise NotFoundError("Tarmoq topilmadi")
        return VenueGroupWithBranchesRead(
            group=VenueGroupRead.model_validate(result.group).model_copy(
                update={"name": result.name}
            ),
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
        return _group_read(updated)


# TODO(service): fixed by the API task — same missing-translation problem as
# `_venue_read`. See DECISIONS.md.
def _group_read(group: VenueGroup, name: str = "") -> VenueGroupRead:
    return VenueGroupRead.model_validate({**group.__dict__, "name": name})
