from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import NotFoundError
from app.core.pagination import Page
from app.modules.catalog.schemas import AmenityRead
from app.modules.staff.services import StaffService
from app.modules.venues.enums import VenueStatus
from app.modules.venues.repositories import VenueRepository
from app.modules.venues.schemas import (
    VenueDetailRead,
    VenueListItem,
    VenuePhotoRead,
    VenueRead,
    VenueSearchParams,
    VenueStatusCountsRead,
    VenueUpdate,
    VenueWorkingHoursRead,
)

PERM_BRANCH_MANAGE = "branch.manage"


class VenueService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.venues = VenueRepository(session)
        self.staff = StaffService(session)

    async def search(
        self, params: VenueSearchParams, local_dt: datetime | None = None
    ) -> Page[VenueListItem]:
        """The home screen.

        `is_open_now` comes back as a computed column rather than a filter unless
        the caller asked for one: a closed venue still belongs on the list with a
        Yopiq badge.
        """
        page = await self.venues.search(
            local_dt=local_dt or utcnow_naive(),
            limit=params.limit,
            offset=params.offset,
            venue_type=params.venue_type,
            district_id=params.district_id,
            guest_count=params.guest_count,
            min_rating=params.min_rating,
            requires_deposit=params.requires_deposit,
            query=params.query,
            latitude=params.latitude,
            longitude=params.longitude,
            radius_m=params.radius_m,
            only_open_now=params.only_open_now,
            sort=params.sort,
        )
        items = [
            VenueListItem(
                id=row.venue.id,
                name=row.name,
                tagline=row.tagline,
                status=VenueStatus(row.venue.status),
                rating_avg=row.venue.rating_avg,
                reviews_count=row.venue.reviews_count,
                base_price=row.venue.base_price,
                currency=row.venue.currency,
                discount_percent=row.venue.discount_percent,
                requires_deposit=row.venue.requires_deposit,
                distance_m=row.distance_m,
                is_open_now=row.is_open_now,
            )
            for row in page.items
        ]
        return Page(items=items, total=page.total, limit=page.limit, offset=page.offset)

    async def get_detail(self, venue_id: int, local_dt: datetime | None = None) -> VenueDetailRead:
        detail = await self.venues.get_detail(venue_id)
        if detail is None:
            raise NotFoundError("Muassasa topilmadi")

        is_open = await self.venues.is_open_at(venue_id, local_dt or utcnow_naive())
        venue = VenueRead.model_validate(detail.venue).model_copy(
            update={
                "name": detail.name,
                "description": detail.description,
                "tagline": detail.tagline,
            }
        )
        return VenueDetailRead(
            venue=venue,
            photos=[VenuePhotoRead.model_validate(photo) for photo in detail.photos],
            amenities=[
                AmenityRead(
                    id=amenity.id,
                    slug=amenity.slug,
                    name=name,
                    icon_url=amenity.icon_url,
                    sort_order=amenity.sort_order,
                )
                for amenity, name in detail.amenities
            ],
            venue_type=detail.venue_type,
            working_hours=[
                VenueWorkingHoursRead(
                    weekday=row.weekday,
                    opens_at=row.opens_at.isoformat() if row.opens_at else None,
                    closes_at=row.closes_at.isoformat() if row.closes_at else None,
                    is_closed=row.is_closed,
                )
                for row in detail.working_hours
            ],
            is_open_now=is_open,
        )

    async def list_for_group(self, group_id: int, status: str | None = None) -> Sequence[VenueRead]:
        venues = await self.venues.list_by_group(group_id, status)
        return [VenueRead.model_validate(venue) for venue in venues]

    async def status_counts(self, group_id: int) -> VenueStatusCountsRead:
        counts = await self.venues.count_by_status_for_group(group_id)
        return VenueStatusCountsRead(total=counts.total, active=counts.active, closed=counts.closed)

    async def update_details(
        self, actor_user_id: int, venue_id: int, payload: VenueUpdate
    ) -> VenueRead:
        await self.staff.require_permission_in_transaction(
            actor_user_id, venue_id, PERM_BRANCH_MANAGE
        )
        updated = await self.venues.update_fields(venue_id, payload.model_dump(exclude_unset=True))
        if updated is None:
            raise NotFoundError("Muassasa topilmadi")
        await self.session.commit()
        return VenueRead.model_validate(updated)

    async def recompute_rating_in_transaction(self, venue_id: int) -> None:
        """Denormalized counters are service-owned; no DB trigger does this."""
        await self.venues.recompute_rating(venue_id)
