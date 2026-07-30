from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Subquery, case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.localization.models import Language
from app.modules.venue_groups.models import VenueGroup, VenueGroupTranslation
from app.modules.venues.models import Venue, VenueTranslation


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

    def _group_translation_subquery(self, language_id: int) -> Subquery:
        priority = case(
            (VenueGroupTranslation.language_id == language_id, 0),
            (Language.code == "uz", 1),
            (Language.code == "en", 2),
            else_=3,
        )
        return (
            select(
                VenueGroupTranslation.venue_group_id.label("venue_group_id"),
                VenueGroupTranslation.name.label("name"),
            )
            .join(Language, Language.id == VenueGroupTranslation.language_id)
            .distinct(VenueGroupTranslation.venue_group_id)
            .order_by(VenueGroupTranslation.venue_group_id, priority)
            .subquery()
        )

    def _branch_translation_subquery(self, language_id: int) -> Subquery:
        priority = case(
            (VenueTranslation.language_id == language_id, 0),
            (Language.code == "uz", 1),
            (Language.code == "en", 2),
            else_=3,
        )
        return (
            select(
                VenueTranslation.venue_id.label("venue_id"),
                VenueTranslation.name.label("name"),
                VenueTranslation.tagline.label("tagline"),
            )
            .join(Language, Language.id == VenueTranslation.language_id)
            .distinct(VenueTranslation.venue_id)
            .order_by(VenueTranslation.venue_id, priority)
            .subquery()
        )

    async def get_by_id(self, group_id: int) -> VenueGroup | None:
        result = await self.session.execute(select(VenueGroup).where(VenueGroup.id == group_id))
        return result.scalar_one_or_none()

    async def get_by_owner(self, owner_id: int) -> VenueGroup | None:
        result = await self.session.execute(
            select(VenueGroup).where(VenueGroup.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def get_with_branches(
        self, group_id: int, language_id: int
    ) -> VenueGroupWithBranches | None:
        group_translations = self._group_translation_subquery(language_id)
        head = await self.session.execute(
            select(VenueGroup, group_translations.c.name)
            .outerjoin(group_translations, group_translations.c.venue_group_id == VenueGroup.id)
            .where(VenueGroup.id == group_id)
        )
        row = head.one_or_none()
        if row is None:
            return None

        branch_translations = self._branch_translation_subquery(language_id)
        branches = await self.session.execute(
            select(Venue, branch_translations.c.name, branch_translations.c.tagline)
            .outerjoin(branch_translations, branch_translations.c.venue_id == Venue.id)
            .where(Venue.venue_group_id == group_id)
            .order_by(Venue.id)
        )
        return VenueGroupWithBranches(
            group=row[0],
            name=row[1] or "",
            branches=[BranchRow(venue=b[0], name=b[1] or "", tagline=b[2]) for b in branches.all()],
        )

    async def create_with_first_branch(
        self,
        group: VenueGroup,
        group_translations: Sequence[VenueGroupTranslation],
        venue: Venue,
        venue_translations: Sequence[VenueTranslation],
    ) -> tuple[VenueGroup, Venue]:
        """Group and first branch in one flush.

        Two flushes are needed only because `venue.venue_group_id` is NOT NULL and
        the group's id is server-generated; both land in the caller's single
        transaction, so nothing is visible until the service commits.
        """
        self.session.add(group)
        await self.session.flush()

        for translation in group_translations:
            translation.venue_group_id = group.id
            self.session.add(translation)

        venue.venue_group_id = group.id
        self.session.add(venue)
        await self.session.flush()

        for venue_translation in venue_translations:
            venue_translation.venue_id = venue.id
            self.session.add(venue_translation)

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

    async def add_translation(self, translation: VenueGroupTranslation) -> VenueGroupTranslation:
        self.session.add(translation)
        await self.session.flush()
        return translation
