from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.schemas import ReadSchema, UpdateSchema
from app.modules.auth.schemas import UserListItem
from app.modules.reviews.enums import ReviewStatus


class ReviewCreate(BaseModel):
    booking_id: int
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)
    photo_urls: list[str] = Field(default_factory=list, max_length=10)


class ReviewUpdate(UpdateSchema):
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewPhotoRead(ReadSchema):
    id: int
    url: str
    sort_order: int


class ReviewListItem(ReadSchema):
    """Tasdiqlangan belgisi `is_verified` — sharh bronga bog'langanini bildiradi."""

    id: int
    rating: int
    comment: str | None = None
    is_verified: bool
    published_at: datetime | None = None
    author: UserListItem
    photos: list[ReviewPhotoRead] = Field(default_factory=list)


class ReviewRead(ReadSchema):
    id: int
    user_id: int
    venue_id: int
    booking_id: int | None = None
    rating: int
    comment: str | None = None
    is_verified: bool
    status: ReviewStatus
    published_at: datetime | None = None


class ReviewAggregateRead(ReadSchema):
    """O'rtacha baho va sharhlar soni — muassasa reytingi shu yerdan qayta hisoblanadi."""

    venue_id: int
    average: Decimal
    count: int
