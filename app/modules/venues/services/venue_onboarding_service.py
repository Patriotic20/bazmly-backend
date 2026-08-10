from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import (
    GroupAlreadyExistsError,
    NotFoundError,
    ValidationFailedError,
)
from app.core.integrity import translate_integrity_error
from app.modules.catalog.repositories import AmenityRepository, VenueTypeRepository
from app.modules.geo.repositories import DistrictRepository
from app.modules.staff.models import VenueStaff
from app.modules.staff.repositories import StaffRoleRepository, VenueStaffRepository
from app.modules.venue_groups.models import VenueGroup, VenueGroupStatus
from app.modules.venue_groups.repositories import VenueGroupRepository
from app.modules.venue_groups.schemas import (
    BranchListItem,
    VenueGroupRead,
    VenueGroupWithBranchCreate,
    VenueGroupWithBranchesRead,
)
from app.modules.venues.enums import VenueStatus
from app.modules.venues.models import Venue, VenueWorkingHours, VenueZone
from app.modules.venues.repositories import (
    VenueRepository,
    VenueWorkingHoursRepository,
    VenueZoneRepository,
    point_ewkt,
)
from app.modules.venues.schemas import (
    VenueCreate,
    VenueRead,
    VenueUpdate,
    WorkingHoursReplace,
)

# The wizard's steps, in the order the screens present them.
STEP_ADDRESS = 1
STEP_HOURS = 2
STEP_TABLES = 3
STEP_SERVICES = 4
STEP_MEDIA = 5
STEP_DONE = 6

# The role the creating user is employed under. Looked up by slug rather than id
# because the seed owns the id and this code does not.
OWNER_ROLE_SLUG = "owner"

# Every branch is born with these. "Umumiy" is not here because it is the
# unfiltered view, not a zone — the same rule as "Barchasi" in the type picker.
DEFAULT_ZONES: tuple[tuple[str, str, int], ...] = (
    ("ichkari", "Ichkari", 1),
    ("tashqari", "Tashqari", 2),
)


class VenueOnboardingService:
    """The multi-step owner wizard, and the only place a branch is born.

    `onboarding_step` exists so a half-finished signup can be resumed rather than
    restarted. Each step advances the counter monotonically — going back and
    re-saving an earlier screen does not rewind it, because the later data is
    already there.

    Both creation paths live here rather than in `VenueService` so that the rules
    a new branch depends on — `location` derived from the coordinates, the owner
    inherited from the chain, the two default zones — exist in exactly one place.
    A branch created without them is not a lesser branch; it is a broken one.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.venues = VenueRepository(session)
        self.hours = VenueWorkingHoursRepository(session)
        self.groups = VenueGroupRepository(session)
        self.zones = VenueZoneRepository(session)
        self.districts = DistrictRepository(session)
        self.venue_types = VenueTypeRepository(session)
        self.amenities = AmenityRepository(session)
        self.staff = VenueStaffRepository(session)
        self.roles = StaffRoleRepository(session)

    async def start(
        self, owner_user_id: int, payload: VenueGroupWithBranchCreate
    ) -> VenueGroupWithBranchesRead:
        """The chain, its first branch and the owner's employment, in one write.

        The employment row is the load-bearing part. Authority is read from
        `venue_staff` on every request and from nowhere else, so an owner who is
        not employed by their own chain cannot edit the branch they just created —
        `users.role` would not save them, because no guard reads it.

        This route cannot be permission-guarded: the caller has no employment row
        yet, which is precisely what it is here to create. One chain per owner is
        what stands in for a guard.
        """
        existing = await self.groups.get_by_owner(owner_user_id)
        if existing is not None:
            raise GroupAlreadyExistsError(details={"group_id": existing.id})

        if await self.venue_types.get_by_id(payload.group.primary_venue_type_id) is None:
            raise NotFoundError("Bunday muassasa turi yo'q")

        owner_role = await self.roles.get_by_slug(OWNER_ROLE_SLUG)
        if owner_role is None:
            raise ValidationFailedError("Rollar sozlanmagan")

        await self._validate_branch_in_transaction(payload.branch)

        group = VenueGroup(
            owner_id=owner_user_id,
            primary_venue_type_id=payload.group.primary_venue_type_id,
            name=payload.group.name,
            description=payload.group.description,
            logo_url=payload.group.logo_url,
            default_currency=payload.group.default_currency,
            status=VenueGroupStatus.DRAFT,
        )
        venue = self._build_branch(payload.branch, owner_id=owner_user_id)

        try:
            group, venue = await self.groups.create_with_first_branch(group, venue)
            await self.staff.create(
                VenueStaff(
                    venue_group_id=group.id,
                    # NULL is the group scope: the owner carries their permissions
                    # at every branch of the chain, including ones not created yet.
                    venue_id=None,
                    user_id=owner_user_id,
                    staff_role_id=owner_role.id,
                    # Read off the role, never hard-coded: `venue_staff` has a
                    # composite FK on (staff_role_id, role_scope), so a mismatch is
                    # rejected by the database rather than stored wrong.
                    role_scope=owner_role.scope,
                    is_active=True,
                    activated_at=utcnow_naive(),
                )
            )
            await self._attach_branch_details_in_transaction(venue.id, payload.branch)
            await self.session.commit()
        except IntegrityError as error:
            raise translate_integrity_error(error) from error

        return VenueGroupWithBranchesRead(
            group=VenueGroupRead.model_validate(group),
            branches=[
                BranchListItem(
                    id=venue.id, name=venue.name, tagline=venue.tagline, status=venue.status
                )
            ],
        )

    async def add_branch(self, group_id: int, payload: VenueCreate) -> VenueRead:
        """The second branch onwards.

        `owner_id` comes from the chain, not from the caller: an admin opening a
        branch does not become its owner.
        """
        group = await self.groups.get_by_id(group_id)
        if group is None:
            raise NotFoundError("Tarmoq topilmadi")

        await self._validate_branch_in_transaction(payload)

        venue = self._build_branch(payload, owner_id=group.owner_id)
        venue.venue_group_id = group.id

        try:
            venue = await self.venues.create(venue)
            await self._attach_branch_details_in_transaction(venue.id, payload)
            await self.session.commit()
        except IntegrityError as error:
            raise translate_integrity_error(error) from error

        return VenueRead.model_validate(venue)

    async def _validate_branch_in_transaction(self, payload: VenueCreate) -> None:
        """Checked before anything is written, in the order that makes the message
        useful: where it is, then what it is, then how big it is."""
        if await self.districts.get_by_id(payload.district_id) is None:
            raise NotFoundError("Bunday tuman yo'q")

        for venue_type_id in payload.venue_type_ids:
            if await self.venue_types.get_by_id(venue_type_id) is None:
                raise NotFoundError(
                    "Bunday muassasa turi yo'q", details={"venue_type_id": venue_type_id}
                )

        minimum, maximum = payload.capacity_min, payload.capacity_max
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValidationFailedError(
                "Eng kam sig'im eng ko'pidan katta bo'lolmaydi",
                details={"capacity_min": minimum, "capacity_max": maximum},
            )

    def _build_branch(self, payload: VenueCreate, owner_id: int) -> Venue:
        """`location` is derived here and never accepted from the client.

        It is NOT NULL with no default, so a branch inserted without it fails; and
        a client-supplied point that disagreed with `latitude`/`longitude` would
        put the map pin and the distance sort in different cities.
        """
        return Venue(
            owner_id=owner_id,
            district_id=payload.district_id,
            street=payload.street,
            house_number=payload.house_number,
            latitude=payload.latitude,
            longitude=payload.longitude,
            location=point_ewkt(payload.latitude, payload.longitude),
            phone=payload.phone,
            name=payload.name,
            description=payload.description,
            tagline=payload.tagline,
            total_seats=payload.total_seats,
            capacity_min=payload.capacity_min,
            capacity_max=payload.capacity_max,
            base_price=payload.base_price,
            currency=payload.currency,
            min_advance_booking_days=payload.min_advance_booking_days,
            late_grace_minutes=payload.late_grace_minutes,
            requires_deposit=payload.requires_deposit,
            deposit_percent=payload.deposit_percent,
            manager_user_id=payload.manager_user_id,
            status=VenueStatus.DRAFT,
            onboarding_step=0,
        )

    async def _attach_branch_details_in_transaction(
        self, venue_id: int, payload: VenueCreate
    ) -> None:
        """Types, amenities and the two default zones. No commit — the caller owns it."""
        for venue_type_id in payload.venue_type_ids:
            await self.venues.add_venue_type(venue_id, venue_type_id)

        if payload.amenity_ids:
            await self.amenities.set_for_venue(venue_id, payload.amenity_ids)

        for slug, name, sort_order in DEFAULT_ZONES:
            await self.zones.create(
                VenueZone(
                    venue_id=venue_id,
                    slug=slug,
                    name=name,
                    sort_order=sort_order,
                    is_active=True,
                )
            )

    async def set_address(self, venue_id: int, payload: VenueUpdate) -> VenueRead:
        return await self._apply_step(
            venue_id, payload.model_dump(exclude_unset=True), STEP_ADDRESS
        )

    async def set_hours_and_seats(
        self, venue_id: int, hours: WorkingHoursReplace, total_seats: int | None = None
    ) -> VenueRead:
        """Onboarding collects one start/end plus a set of weekdays; that writes
        the whole week at once."""
        rows = [
            VenueWorkingHours(
                venue_id=venue_id,
                weekday=day.weekday,
                opens_at=day.opens_at,
                closes_at=day.closes_at,
                is_closed=day.is_closed,
            )
            for day in hours.days
        ]
        await self.hours.replace_all(venue_id, rows)
        values: dict[str, object] = {}
        if total_seats is not None:
            values["total_seats"] = total_seats
        return await self._apply_step(venue_id, values, STEP_HOURS)

    async def mark_tables_done(self, venue_id: int) -> VenueRead:
        return await self._apply_step(venue_id, {}, STEP_TABLES)

    async def mark_services_done(self, venue_id: int) -> VenueRead:
        return await self._apply_step(venue_id, {}, STEP_SERVICES)

    async def mark_media_done(self, venue_id: int) -> VenueRead:
        return await self._apply_step(venue_id, {}, STEP_MEDIA)

    async def finish(self, venue_id: int) -> VenueRead:
        """ "Restaurant is live" — status and `onboarded_at` in one write.

        Refuses if earlier steps are unfinished, so a branch cannot go live without
        the hours that the open/closed badge is computed from.
        """
        venue = await self.venues.get_by_id(venue_id)
        if venue is None:
            raise NotFoundError("Muassasa topilmadi")
        if venue.onboarding_step < STEP_MEDIA:
            raise ValidationFailedError(
                "Avval oldingi sozlash bosqichlarini yakunlang",
                details={"current_step": venue.onboarding_step, "required": STEP_MEDIA},
            )

        updated = await self.venues.update_fields(
            venue_id,
            {
                "status": VenueStatus.ACTIVE,
                "onboarded_at": utcnow_naive(),
                "onboarding_step": STEP_DONE,
            },
        )
        if updated is None:
            raise NotFoundError("Muassasa topilmadi")
        await self.session.commit()
        return VenueRead.model_validate(updated)

    async def _apply_step(self, venue_id: int, values: dict[str, object], step: int) -> VenueRead:
        venue = await self.venues.get_by_id(venue_id)
        if venue is None:
            raise NotFoundError("Muassasa topilmadi")

        values = dict(values)
        values["onboarding_step"] = max(venue.onboarding_step, step)
        updated = await self.venues.update_fields(venue_id, values)
        if updated is None:
            raise NotFoundError("Muassasa topilmadi")
        await self.session.commit()
        return VenueRead.model_validate(updated)
