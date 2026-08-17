from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Select,
    case,
    func,
    literal,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.geo import haversine_distance_m
from app.core.pagination import Page
from app.modules.catalog.models import Amenity
from app.modules.reviews.models import Review, ReviewStatus
from app.modules.venues.enums import VenueTypeSlug
from app.modules.venues.models import (
    Venue,
    VenueAmenity,
    VenuePhoto,
    VenueStatus,
    VenueWorkingHours,
)
from app.modules.venues.models.venue_special_day import VenueSpecialDay

# Below this trigram similarity a hit is noise rather than a transliteration
# variant. `%` uses the GIN index; the threshold is applied on top of it.
NAME_SIMILARITY_THRESHOLD = 0.15

SORT_DISTANCE = "distance"
SORT_RATING = "rating"
SORT_PRICE = "price"


def venue_distance_m(latitude: float, longitude: float) -> ColumnElement[float]:
    """Great-circle distance from a point to `venues`, in metres.

    A thin name over the shared helper, kept because "distance to a venue" reads
    better at every call site than the four-argument general form.
    """
    return haversine_distance_m(latitude, longitude, Venue.latitude, Venue.longitude)


@dataclass(frozen=True, slots=True)
class VenueSearchRow:
    """One home-screen card.

    `distance_m` and `is_open_now` are computed by the database per row. They are
    not attributes of `Venue` and are deliberately not bolted onto the ORM object,
    where they would silently become stale or absent depending on how the venue
    was loaded.
    """

    venue: Venue
    name: str
    tagline: str | None
    distance_m: float | None
    is_open_now: bool


@dataclass(frozen=True, slots=True)
class VenueDetail:
    venue: Venue
    name: str
    description: str | None
    tagline: str | None
    photos: Sequence[VenuePhoto]
    amenities: Sequence[tuple[Amenity, str]]
    venue_type: VenueTypeSlug
    working_hours: Sequence[VenueWorkingHours]


@dataclass(frozen=True, slots=True)
class VenueStatusCounts:
    """The Filiallar header: Jami / Aktiv / Yopiq."""

    total: int
    active: int
    closed: int


class VenueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _is_open_now_expression(self, local_dt: datetime) -> ColumnElement[bool]:
        """Open right now, from working hours with a special-day override.

        This is `venues.status`'s opposite number and the two must not be confused:
        `status` is administrative and persistent, this is the clock. A special day
        wins outright — a holiday closure inside normal hours still reads closed.
        """
        local_date = local_dt.date()
        local_time = local_dt.time()
        weekday = local_dt.weekday()  # Monday = 0, matching venue_working_hours

        special_day = (
            select(
                case(
                    (VenueSpecialDay.is_closed.is_(True), literal(False)),
                    (
                        VenueSpecialDay.opens_at.is_(None) | VenueSpecialDay.closes_at.is_(None),
                        literal(False),
                    ),
                    else_=literal(local_time).between(
                        VenueSpecialDay.opens_at, VenueSpecialDay.closes_at
                    ),
                )
            )
            .where(
                VenueSpecialDay.venue_id == Venue.id,
                VenueSpecialDay.date == local_date,
            )
            .limit(1)
            .correlate(Venue)
            .scalar_subquery()
        )

        working_hours = (
            select(
                case(
                    (VenueWorkingHours.is_closed.is_(True), literal(False)),
                    (
                        VenueWorkingHours.opens_at.is_(None)
                        | VenueWorkingHours.closes_at.is_(None),
                        literal(False),
                    ),
                    else_=literal(local_time).between(
                        VenueWorkingHours.opens_at, VenueWorkingHours.closes_at
                    ),
                )
            )
            .where(
                VenueWorkingHours.venue_id == Venue.id,
                VenueWorkingHours.weekday == weekday,
            )
            .limit(1)
            .correlate(Venue)
            .scalar_subquery()
        )

        return func.coalesce(special_day, working_hours, literal(False))

    def _search_statement(
        self,
        *,
        local_dt: datetime,
        venue_type: VenueTypeSlug | None,
        district_id: int | None,
        guest_count: int | None,
        min_rating: Decimal | None,
        requires_deposit: bool | None,
        query: str | None,
        latitude: float | None,
        longitude: float | None,
        radius_m: float | None,
        only_open_now: bool,
    ) -> Select[tuple[Venue, str, str | None, float | None, bool]]:

        near = (
            venue_distance_m(latitude, longitude)
            if latitude is not None and longitude is not None
            else None
        )
        distance = (
            near.label("distance_m") if near is not None else literal(None).label("distance_m")
        )
        is_open_now = self._is_open_now_expression(local_dt).label("is_open_now")

        stmt = select(
            Venue,
            Venue.name,
            Venue.tagline,
            distance,
            is_open_now,
        ).where(Venue.status == VenueStatus.ACTIVE)

        if near is not None and radius_m is not None:
            stmt = stmt.where(near <= radius_m)

        if venue_type is not None:
            stmt = stmt.where(Venue.venue_type == venue_type)

        if district_id is not None:
            stmt = stmt.where(Venue.district_id == district_id)

        if guest_count is not None:
            # Covers both shapes: a to'yxona advertises a capacity range, a
            # restaurant usually leaves it null and is filtered by table instead.
            stmt = stmt.where(
                (Venue.capacity_min.is_(None)) | (Venue.capacity_min <= guest_count)
            ).where((Venue.capacity_max.is_(None)) | (Venue.capacity_max >= guest_count))

        if min_rating is not None:
            stmt = stmt.where(Venue.rating_avg >= min_rating)

        if requires_deposit is not None:
            stmt = stmt.where(Venue.requires_deposit.is_(requires_deposit))

        if query:
            # `%` is the pg_trgm operator backed by the GIN index on the name.
            stmt = stmt.where(
                Venue.name.op("%")(query)
                | (func.similarity(Venue.name, query) >= NAME_SIMILARITY_THRESHOLD)
            )

        if only_open_now:
            stmt = stmt.where(is_open_now)

        return stmt

    async def search(
        self,
        *,
        local_dt: datetime,
        limit: int = 20,
        offset: int = 0,
        venue_type: VenueTypeSlug | None = None,
        district_id: int | None = None,
        guest_count: int | None = None,
        min_rating: Decimal | None = None,
        requires_deposit: bool | None = None,
        query: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_m: float | None = None,
        only_open_now: bool = False,
        sort: str = SORT_RATING,
    ) -> Page[VenueSearchRow]:
        """The customer home screen, as one statement.

        `is_open_now` is a computed column, not a filter, unless `only_open_now` is
        asked for — a closed venue still belongs on the list with a Yopiq badge.
        """
        stmt = self._search_statement(
            local_dt=local_dt,
            venue_type=venue_type,
            district_id=district_id,
            guest_count=guest_count,
            min_rating=min_rating,
            requires_deposit=requires_deposit,
            query=query,
            latitude=latitude,
            longitude=longitude,
            radius_m=radius_m,
            only_open_now=only_open_now,
        )

        if sort == SORT_DISTANCE and latitude is not None and longitude is not None:
            stmt = stmt.order_by(venue_distance_m(latitude, longitude).asc(), Venue.id)
        elif sort == SORT_PRICE:
            stmt = stmt.order_by(Venue.base_price.asc().nulls_last(), Venue.id)
        else:
            stmt = stmt.order_by(Venue.rating_avg.desc(), Venue.reviews_count.desc(), Venue.id)

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        result = await self.session.execute(stmt.limit(limit).offset(offset))
        rows = [
            VenueSearchRow(
                venue=row[0],
                name=row[1] or "",
                tagline=row[2],
                distance_m=float(row[3]) if row[3] is not None else None,
                is_open_now=bool(row[4]),
            )
            for row in result.all()
        ]
        return Page(items=rows, total=total, limit=limit, offset=offset)

    async def get_by_id(self, venue_id: int) -> Venue | None:
        result = await self.session.execute(select(Venue).where(Venue.id == venue_id))
        return result.scalar_one_or_none()

    async def get_detail(self, venue_id: int) -> VenueDetail | None:
        """Venue plus every child collection the detail screen renders.

        Each collection is fetched explicitly rather than through `selectinload`,
        because the models declare no relationships — see REPOSITORY_PLAN.md.

        `venue_type` costs no query: it arrives on the venue row itself, where the
        lookup table and its join used to need a fourth round trip.
        """
        head = await self.session.execute(
            select(
                Venue,
                Venue.name,
                Venue.description,
                Venue.tagline,
            ).where(Venue.id == venue_id)
        )
        row = head.one_or_none()
        if row is None:
            return None

        photos = await self.session.execute(
            select(VenuePhoto)
            .where(VenuePhoto.venue_id == venue_id)
            .order_by(VenuePhoto.is_cover.desc(), VenuePhoto.sort_order)
        )

        amenities = await self.session.execute(
            select(Amenity)
            .join(VenueAmenity, VenueAmenity.amenity_id == Amenity.id)
            .where(VenueAmenity.venue_id == venue_id)
            .order_by(Amenity.sort_order)
        )

        working_hours = await self.session.execute(
            select(VenueWorkingHours)
            .where(VenueWorkingHours.venue_id == venue_id)
            .order_by(VenueWorkingHours.weekday)
        )

        return VenueDetail(
            venue=row[0],
            name=row[1] or "",
            description=row[2],
            tagline=row[3],
            photos=photos.scalars().all(),
            amenities=[(a, a.name or a.slug) for a in amenities.scalars().all()],
            venue_type=VenueTypeSlug(row[0].venue_type),
            working_hours=working_hours.scalars().all(),
        )

    async def list_by_group(self, group_id: int, status: str | None = None) -> Sequence[Venue]:
        stmt = select(Venue).where(Venue.venue_group_id == group_id)
        if status is not None:
            stmt = stmt.where(Venue.status == status)
        result = await self.session.execute(stmt.order_by(Venue.id))
        return result.scalars().all()

    async def count_by_status_for_group(self, group_id: int) -> VenueStatusCounts:
        """Jami / Aktiv / Yopiq in one grouped pass, not three round trips."""
        result = await self.session.execute(
            select(Venue.status, func.count())
            .where(Venue.venue_group_id == group_id)
            .group_by(Venue.status)
        )
        counts = {status: int(count) for status, count in result.all()}
        return VenueStatusCounts(
            total=sum(counts.values()),
            active=counts.get(VenueStatus.ACTIVE, 0),
            closed=counts.get(VenueStatus.CLOSED, 0),
        )

    async def is_open_at(self, venue_id: int, local_dt: datetime) -> bool:
        result = await self.session.execute(
            select(self._is_open_now_expression(local_dt)).where(Venue.id == venue_id)
        )
        return bool(result.scalar_one_or_none())

    async def recompute_rating(self, venue_id: int) -> Venue | None:
        """Denormalized counters are service-owned; this is the one statement that
        owns them. No trigger, per the schema's design decision 12."""
        aggregate = (
            select(
                func.coalesce(func.avg(Review.rating), 0).label("avg_rating"),
                func.count().label("review_count"),
            )
            .where(Review.venue_id == venue_id, Review.status == ReviewStatus.PUBLISHED)
            .subquery()
        )
        result = await self.session.execute(
            update(Venue)
            .where(Venue.id == venue_id)
            .values(
                rating_avg=select(aggregate.c.avg_rating).scalar_subquery(),
                reviews_count=select(aggregate.c.review_count).scalar_subquery(),
            )
            .returning(Venue)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def create(self, venue: Venue) -> Venue:
        self.session.add(venue)
        await self.session.flush()
        return venue

    async def set_status(self, venue_id: int, status: str) -> Venue | None:
        result = await self.session.execute(
            update(Venue).where(Venue.id == venue_id).values(status=status).returning(Venue)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def update_fields(self, venue_id: int, values: dict[str, Any]) -> Venue | None:
        """Partial update from an already-validated `VenueUpdate`.

        Empty `values` is a no-op returning the row, so a caller that filtered
        everything out does not issue an `UPDATE ... SET` with nothing to set.
        """
        if not values:
            return await self.get_by_id(venue_id)
        result = await self.session.execute(
            update(Venue).where(Venue.id == venue_id).values(**values).returning(Venue)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def add_photo(self, photo: VenuePhoto) -> VenuePhoto:
        self.session.add(photo)
        await self.session.flush()
        return photo

    async def list_photos(self, venue_id: int) -> Sequence[VenuePhoto]:
        result = await self.session.execute(
            select(VenuePhoto)
            .where(VenuePhoto.venue_id == venue_id)
            .order_by(VenuePhoto.is_cover.desc(), VenuePhoto.sort_order)
        )
        return result.scalars().all()
