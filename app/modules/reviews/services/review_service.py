from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import (
    AlreadyReviewedError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.core.pagination import Page
from app.modules.auth.schemas import UserListItem
from app.modules.bookings.enums import BookingStatus
from app.modules.bookings.repositories import BookingRepository
from app.modules.reviews.enums import ReviewStatus
from app.modules.reviews.models import Review
from app.modules.reviews.repositories import ReviewRepository
from app.modules.reviews.schemas import (
    ReviewAggregateRead,
    ReviewCreate,
    ReviewListItem,
    ReviewPhotoRead,
    ReviewRead,
)
from app.modules.venues.repositories import VenueRepository


class ReviewService:
    """A review is tied to a completed visit, not to an opinion.

    Only the guest who made a `completed` booking may review it, and only once —
    which is what the "Verified" badge means and why `booking_id` is unique.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.reviews = ReviewRepository(session)
        self.bookings = BookingRepository(session)
        self.venues = VenueRepository(session)

    async def create(self, user_id: int, payload: ReviewCreate) -> ReviewRead:
        booking = await self.bookings.get_by_id(payload.booking_id)
        if booking is None:
            raise NotFoundError("Booking not found")
        if booking.user_id != user_id:
            raise PermissionDeniedError("That booking belongs to someone else")
        if booking.status != BookingStatus.COMPLETED:
            raise ValidationFailedError(
                "You can review a visit only after it is completed",
                details={"status": booking.status},
            )

        existing = await self.reviews.get_by_booking(payload.booking_id)
        if existing is not None:
            raise AlreadyReviewedError()

        review = await self.reviews.create(
            Review(
                user_id=user_id,
                venue_id=booking.venue_id,
                booking_id=booking.id,
                rating=payload.rating,
                comment=payload.comment,
                is_verified=True,
                status=ReviewStatus.PENDING,
            )
        )
        if payload.photo_urls:
            await self.reviews.add_photos(review.id, payload.photo_urls)
        await self.session.commit()
        return ReviewRead.model_validate(review)

    async def publish(self, review_id: int) -> ReviewRead:
        """Publishing and the venue's rating recompute share one transaction.

        Splitting them would leave a window where a published review is not
        reflected in the rating a customer is looking at.
        """
        review = await self.reviews.get_by_id(review_id)
        if review is None:
            raise NotFoundError("Review not found")

        updated = await self.reviews.set_status(review_id, ReviewStatus.PUBLISHED, utcnow_naive())
        if updated is None:
            raise NotFoundError("Review not found")
        await self.venues.recompute_rating(review.venue_id)
        await self.session.commit()
        return ReviewRead.model_validate(updated)

    async def list_for_venue(
        self, venue_id: int, limit: int = 20, offset: int = 0
    ) -> Page[ReviewListItem]:
        page = await self.reviews.list_for_venue(venue_id, limit, offset)
        items = [
            ReviewListItem(
                id=row.review.id,
                rating=row.review.rating,
                comment=row.review.comment,
                is_verified=row.review.is_verified,
                published_at=row.review.published_at,
                author=UserListItem.model_validate(row.author),
                photos=[ReviewPhotoRead.model_validate(photo) for photo in row.photos],
            )
            for row in page.items
        ]
        return Page(items=items, total=page.total, limit=page.limit, offset=page.offset)

    async def aggregate(self, venue_id: int) -> ReviewAggregateRead:
        result = await self.reviews.aggregate_for_venue(venue_id)
        return ReviewAggregateRead(venue_id=venue_id, average=result.average, count=result.count)
