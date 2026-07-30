from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.modules.venues.enums import VenueStatus
from app.modules.venues.models import Venue, VenueWorkingHours
from app.modules.venues.repositories import (
    VenueRepository,
    VenueWorkingHoursRepository,
)
from app.modules.venues.schemas import (
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


class VenueOnboardingService:
    """The multi-step owner wizard.

    `onboarding_step` exists so a half-finished signup can be resumed rather than
    restarted. Each step advances the counter monotonically — going back and
    re-saving an earlier screen does not rewind it, because the later data is
    already there.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.venues = VenueRepository(session)
        self.hours = VenueWorkingHoursRepository(session)

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
            raise NotFoundError("Venue not found")
        if venue.onboarding_step < STEP_MEDIA:
            raise ValidationFailedError(
                "Finish the earlier onboarding steps first",
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
            raise NotFoundError("Venue not found")
        await self.session.commit()
        return _venue_read(updated)

    async def _apply_step(self, venue_id: int, values: dict[str, object], step: int) -> VenueRead:
        venue = await self.venues.get_by_id(venue_id)
        if venue is None:
            raise NotFoundError("Venue not found")

        values = dict(values)
        values["onboarding_step"] = max(venue.onboarding_step, step)
        updated = await self.venues.update_fields(venue_id, values)
        if updated is None:
            raise NotFoundError("Venue not found")
        await self.session.commit()
        return _venue_read(updated)


# TODO(service): fixed by the API task — `VenueRead.name` is a resolved
# translation, not a column, so `model_validate` on the ORM row failed on a
# missing required field before `model_copy` could supply it. See DECISIONS.md.
def _venue_read(venue: Venue, name: str = "") -> VenueRead:
    """Build the schema with the translated name supplied explicitly.

    Callers that know the language use `get_detail`, which resolves the real name;
    these paths return the row itself and leave naming to the caller.
    """
    return VenueRead.model_validate({**venue.__dict__, "name": name})
