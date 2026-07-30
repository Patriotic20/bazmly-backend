from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page
from app.modules.auth.models import User
from app.modules.reviews.models import Review, ReviewPhoto, ReviewStatus


@dataclass(frozen=True, slots=True)
class ReviewRow:
    review: Review
    author: User
    photos: Sequence[ReviewPhoto]


@dataclass(frozen=True, slots=True)
class ReviewAggregate:
    average: Decimal
    count: int


class ReviewRepository:
    """The "Verified" badge is `booking_id IS NOT NULL`; the unique constraint on
    that column gives one review per completed booking."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, review_id: int) -> Review | None:
        result = await self.session.execute(select(Review).where(Review.id == review_id))
        return result.scalar_one_or_none()

    async def get_by_booking(self, booking_id: int) -> Review | None:
        result = await self.session.execute(select(Review).where(Review.booking_id == booking_id))
        return result.scalar_one_or_none()

    async def list_for_venue(
        self, venue_id: int, limit: int = 20, offset: int = 0
    ) -> Page[ReviewRow]:
        """Published reviews with their author and photos.

        Photos are fetched in one extra statement keyed by the page's review ids,
        rather than per review — the page is bounded, so this is two round trips
        regardless of page size.
        """
        filters = (Review.venue_id == venue_id, Review.status == ReviewStatus.PUBLISHED)

        total = int(
            (
                await self.session.execute(select(func.count()).select_from(Review).where(*filters))
            ).scalar_one()
        )

        result = await self.session.execute(
            select(Review, User)
            .join(User, User.id == Review.user_id)
            .where(*filters)
            .order_by(Review.published_at.desc().nulls_last(), Review.id.desc())
            .limit(limit)
            .offset(offset)
        )
        pairs = result.all()
        review_ids = [pair[0].id for pair in pairs]

        photos_by_review: dict[int, list[ReviewPhoto]] = {rid: [] for rid in review_ids}
        if review_ids:
            photo_result = await self.session.execute(
                select(ReviewPhoto)
                .where(ReviewPhoto.review_id.in_(review_ids))
                .order_by(ReviewPhoto.sort_order, ReviewPhoto.id)
            )
            for photo in photo_result.scalars().all():
                photos_by_review[photo.review_id].append(photo)

        rows = [
            ReviewRow(review=pair[0], author=pair[1], photos=photos_by_review[pair[0].id])
            for pair in pairs
        ]
        return Page(items=rows, total=total, limit=limit, offset=offset)

    async def aggregate_for_venue(self, venue_id: int) -> ReviewAggregate:
        """Average and count in one pass — the source of truth that
        `VenueRepository.recompute_rating` writes into the denormalized columns."""
        result = await self.session.execute(
            select(
                func.coalesce(func.avg(Review.rating), 0),
                func.count(),
            ).where(Review.venue_id == venue_id, Review.status == ReviewStatus.PUBLISHED)
        )
        row = result.one()
        return ReviewAggregate(average=Decimal(row[0]), count=int(row[1]))

    async def list_pending(self, limit: int = 50, offset: int = 0) -> Sequence[Review]:
        result = await self.session.execute(
            select(Review)
            .where(Review.status == ReviewStatus.PENDING)
            .order_by(Review.created_at)
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def create(self, review: Review) -> Review:
        self.session.add(review)
        await self.session.flush()
        return review

    async def set_status(
        self, review_id: int, status: str, now: datetime | None = None
    ) -> Review | None:
        values: dict[str, object] = {"status": status}
        if status == ReviewStatus.PUBLISHED:
            values["published_at"] = now
        result = await self.session.execute(
            update(Review).where(Review.id == review_id).values(**values).returning(Review)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def add_photos(self, review_id: int, urls: Sequence[str]) -> Sequence[ReviewPhoto]:
        photos = [
            ReviewPhoto(review_id=review_id, url=url, sort_order=index)
            for index, url in enumerate(urls)
        ]
        for photo in photos:
            self.session.add(photo)
        await self.session.flush()
        return photos

    async def anonymise_for_user(self, user_id: int) -> Sequence[int]:
        """Account deletion keeps the review, drops the authorship link.

        The rating still counts toward the venue's average — removing it would
        rewrite history for every other reader — but the text is no longer
        attributable.
        """
        result = await self.session.execute(
            update(Review)
            .where(Review.user_id == user_id)
            .values(comment=None)
            .returning(Review.id)
        )
        await self.session.flush()
        return list(result.scalars().all())
