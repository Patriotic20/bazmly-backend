from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.schemas import Money, PhoneNumber, ReadSchema, UpdateSchema
from app.modules.catalog.schemas import AmenityRead, VenueTypeRead
from app.modules.venues.enums import VenueStatus

SORT_DISTANCE = "distance"
SORT_RATING = "rating"
SORT_PRICE = "price"


class VenueCreate(BaseModel):
    venue_group_id: int
    district_id: int
    street: str = Field(min_length=1, max_length=255)
    house_number: str = Field(min_length=1, max_length=50)
    latitude: Decimal
    longitude: Decimal
    phone: PhoneNumber
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    tagline: str | None = Field(default=None, max_length=120)
    venue_type_ids: list[int] = Field(default_factory=list)
    total_seats: int | None = Field(default=None, gt=0)
    capacity_min: int | None = Field(default=None, gt=0)
    capacity_max: int | None = Field(default=None, gt=0)
    base_price: Money | None = None
    currency: str = "UZS"
    min_advance_booking_days: int = Field(default=1, ge=0, le=30)
    late_grace_minutes: int = Field(default=40, ge=0, le=240)
    requires_deposit: bool = False
    deposit_percent: Decimal | None = Field(default=None, ge=0, le=100)
    manager_user_id: int | None = None


class VenueUpdate(UpdateSchema):
    district_id: int | None = None
    street: str | None = Field(default=None, min_length=1, max_length=255)
    house_number: str | None = Field(default=None, min_length=1, max_length=50)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    phone: PhoneNumber | None = None
    total_seats: int | None = Field(default=None, gt=0)
    capacity_min: int | None = Field(default=None, gt=0)
    capacity_max: int | None = Field(default=None, gt=0)
    base_price: Money | None = None
    min_advance_booking_days: int | None = Field(default=None, ge=0, le=30)
    late_grace_minutes: int | None = Field(default=None, ge=0, le=240)
    requires_deposit: bool | None = None
    deposit_percent: Decimal | None = Field(default=None, ge=0, le=100)
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    manager_user_id: int | None = None
    status: VenueStatus | None = None


class VenueListItem(ReadSchema):
    """Bosh ekran yoki Filiallar kartasi.

    `distance_m` va `is_open_now` har bir qator uchun ma'lumotlar bazasida
    hisoblanadi. `is_open_now` — soat bo'yicha holat, `status` esa ma'muriy
    holat. Kartada ikkalasi bitta belgida ko'rinadi, API da esa ajratilgan.
    """

    id: int
    name: str
    tagline: str | None = None
    status: VenueStatus
    rating_avg: Decimal
    reviews_count: int
    base_price: Money | None = None
    currency: str
    discount_percent: Decimal | None = None
    requires_deposit: bool
    distance_m: float | None = None
    is_open_now: bool = False


class VenueRead(ReadSchema):
    id: int
    venue_group_id: int
    name: str
    description: str | None = None
    tagline: str | None = None
    district_id: int
    street: str
    house_number: str
    latitude: Decimal
    longitude: Decimal
    phone: str
    total_seats: int | None = None
    capacity_min: int | None = None
    capacity_max: int | None = None
    base_price: Money | None = None
    currency: str
    min_advance_booking_days: int
    late_grace_minutes: int
    requires_deposit: bool
    deposit_percent: Decimal | None = None
    discount_percent: Decimal | None = None
    rating_avg: Decimal
    reviews_count: int
    status: VenueStatus
    onboarding_step: int
    onboarded_at: datetime | None = None


class VenuePhotoRead(ReadSchema):
    id: int
    url: str
    sort_order: int
    is_cover: bool


class VenueWorkingHoursRead(ReadSchema):
    weekday: int
    opens_at: str | None = None
    closes_at: str | None = None
    is_closed: bool


class VenueDetailRead(ReadSchema):
    """Muassasa sahifasi — server tomonidan alohida so'rovlardan yig'iladi."""

    venue: VenueRead
    photos: list[VenuePhotoRead]
    amenities: list[AmenityRead]
    venue_types: list[VenueTypeRead]
    working_hours: list[VenueWorkingHoursRead]
    is_open_now: bool = False


class VenueSearchParams(BaseModel):
    """Bosh ekran filtrlari — o'n beshta alohida parametr o'rniga bitta obyekt."""

    query: str | None = Field(default=None, max_length=255)
    venue_type_ids: list[int] | None = None
    district_id: int | None = None
    guest_count: int | None = Field(default=None, gt=0)
    min_rating: Decimal | None = Field(default=None, ge=0, le=5)
    requires_deposit: bool | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_m: float | None = Field(default=None, gt=0)
    only_open_now: bool = False
    sort: str = SORT_RATING
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class VenueStatusCountsRead(ReadSchema):
    """Filiallar sarlavhasidagi Jami / Aktiv / Yopiq."""

    total: int
    active: int
    closed: int
