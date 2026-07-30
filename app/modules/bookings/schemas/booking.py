from datetime import date, datetime, time
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import Money, PhoneNumber, PromoCodeStr, ReadSchema, UpdateSchema
from app.modules.bookings.enums import BookingKind, BookingStatus
from app.modules.bookings.schemas.booking_item import BookingItemCreate, BookingItemRead
from app.modules.bookings.schemas.booking_service import (
    BookingServiceCreate,
    BookingServiceRead,
)
from app.modules.bookings.schemas.price_line import PriceLineRead


class _BookingCreateBase(BaseModel):
    """Fields shared by both kinds.

    `booking_date` is a `date` and the times are `time`, never a combined
    `datetime`: 11:00 at the venue must stay 11:00 regardless of the reader's
    timezone. UTC applies only to audit stamps.
    """

    venue_id: int
    booking_date: date
    start_time: time
    end_time: time
    guests_count: int = Field(gt=0)
    contact_name: str = Field(min_length=1, max_length=200)
    contact_phone: PhoneNumber
    note: str | None = None
    promo_code: PromoCodeStr | None = None
    services: list[BookingServiceCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _times_are_ordered(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class TableReservationCreate(_BookingCreateBase):
    """Restaurant reservation. Carries a table and an optional menu pre-order."""

    table_id: int
    items: list[BookingItemCreate] = Field(default_factory=list)


class HallEventCreate(_BookingCreateBase):
    """To'yxona event. The guest tier is resolved from `guests_count` by the
    service, so the client never picks a price band itself."""

    venue_service_ids: list[int] = Field(default_factory=list)


class BookingUpdate(UpdateSchema):
    contact_name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_phone: PhoneNumber | None = None
    note: str | None = None
    guests_count: int | None = Field(default=None, gt=0)


class BookingCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class BookingListItem(ReadSchema):
    """A Joylar card. Deliberately no `qr_token` — a list is rendered in places a
    screenshot is cheap, and the token is a bearer credential for check-in."""

    id: int
    venue_id: int
    venue_name: str
    kind: BookingKind
    status: BookingStatus
    booking_date: date
    start_time: time
    end_time: time
    guests_count: int
    total_amount: Money
    currency: str
    table_number: int | None = None


class BookingRead(ReadSchema):
    """The venue-side view of a booking. Still no `qr_token`."""

    id: int
    user_id: int
    venue_id: int
    kind: BookingKind
    status: BookingStatus
    booking_date: date
    start_time: time
    end_time: time
    guests_count: int
    contact_name: str
    contact_phone: str
    note: str | None = None
    subtotal: Money
    discount_amount: Money
    deposit_amount: Money
    total_amount: Money
    currency: str
    receipt_number: str
    ticket_code: str
    table_id: int | None = None
    guest_tier_id: int | None = None
    auto_cancel_at: datetime | None = None
    confirmed_at: datetime | None = None
    checked_in_at: datetime | None = None
    checked_out_at: datetime | None = None
    seated_minutes: int | None = None
    cancelled_at: datetime | None = None
    completed_at: datetime | None = None


class BookingOwnerDetail(ReadSchema):
    """The booking owner's own detail response — the only schema carrying
    `qr_token`.

    The token is shown *by* the customer *to* the venue and is single-use. It
    never appears in a list, and never in any venue-side response.
    """

    booking: BookingRead
    qr_token: str
    venue_name: str
    items: list[BookingItemRead] = Field(default_factory=list)
    services: list[BookingServiceRead] = Field(default_factory=list)
    price_lines: list[PriceLineRead] = Field(default_factory=list)


class BookingSearchParams(BaseModel):
    statuses: list[BookingStatus] | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PriceQuote(ReadSchema):
    """What the wizard shows before anything is written."""

    subtotal: Money
    discount_amount: Money
    deposit_amount: Money
    total_amount: Money
    currency: str
    lines: list[PriceLineRead] = Field(default_factory=list)


class BlockedDatesRead(ReadSchema):
    """The greyed-out chips in the date picker."""

    venue_id: int
    dates: list[date]


class AvailableTableRead(ReadSchema):
    id: int
    number: int
    seats: int
    zone_id: int | None = None


class CheckInRequest(BaseModel):
    qr_token: str = Field(min_length=1, max_length=32)
    venue_id: int


class SeatedSummary(ReadSchema):
    booking_id: int
    checked_in_at: datetime | None = None
    checked_out_at: datetime | None = None
    seated_minutes: int | None = None


class DepositPolicy(ReadSchema):
    requires_deposit: bool
    deposit_percent: Decimal | None = None
    deposit_amount: Money
