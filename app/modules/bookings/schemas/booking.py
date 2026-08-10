from datetime import date, datetime, time
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import Money, PhoneNumber, ReadSchema, UpdateSchema
from app.modules.bookings.enums import BookingKind, BookingStatus
from app.modules.bookings.schemas.booking_item import BookingItemCreate, BookingItemRead
from app.modules.bookings.schemas.booking_service import (
    BookingServiceCreate,
    BookingServiceRead,
)
from app.modules.bookings.schemas.price_line import PriceLineRead


class _BookingCreateBase(BaseModel):
    """Ikki xil bron uchun umumiy maydonlar.

    `booking_date` — sana, vaqtlar esa `time`. Ular hech qachon bitta
    `datetime` ga birlashtirilmaydi: muassasadagi 11:00 o'quvchining vaqt
    mintaqasidan qat'i nazar 11:00 bo'lib qolishi kerak.
    """

    venue_id: int
    booking_date: date
    start_time: time
    end_time: time
    guests_count: int = Field(gt=0)
    contact_name: str = Field(min_length=1, max_length=200)
    contact_phone: PhoneNumber
    note: str | None = None
    services: list[BookingServiceCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _times_are_ordered(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("`end_time` `start_time` dan keyin bo'lishi kerak")
        return self


class TableReservationCreate(_BookingCreateBase):
    """Restoran stoli broni. Stol va ixtiyoriy menyu buyurtmasi bilan."""

    table_id: int
    items: list[BookingItemCreate] = Field(default_factory=list)


class HallEventCreate(_BookingCreateBase):
    """To'yxona tadbiri. Narx bosqichi `guests_count` asosida serverda aniqlanadi,
    mijoz o'zi tanlamaydi.
    """

    venue_service_ids: list[int] = Field(default_factory=list)


class BookingUpdate(UpdateSchema):
    contact_name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_phone: PhoneNumber | None = None
    note: str | None = None
    guests_count: int | None = Field(default=None, gt=0)


class BookingCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class BookingListItem(ReadSchema):
    """Joylar bo'limidagi karta.

    `qr_token` ataylab qaytarilmaydi — ro'yxatni skrinshot qilish oson, token
    esa kelishni qayd etish uchun kalit.
    """

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
    """Bronning muassasa tomonidan ko'riniladigan ma'lumoti. `qr_token` bu yerda ham yo'q."""

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
    """Mijozning o'z broni — `qr_token` faqat shu javobda qaytariladi.

    Tokenni mijoz muassasaga ko'rsatadi va u bir marta ishlatiladi. Hech qanday
    ro'yxatda va muassasa tomonidagi javoblarda ko'rinmaydi.
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
    """Bron yozilishidan oldin ko'rsatiladigan narx hisobi.

    `deposit_amount` — `total_amount` ning oldindan to'lanadigan qismi, unga
    qo'shimcha emas; shuning uchun u yig'indini oshirmaydi.
    """

    subtotal: Money
    deposit_amount: Money
    total_amount: Money
    currency: str
    lines: list[PriceLineRead] = Field(default_factory=list)


class BlockedDatesRead(ReadSchema):
    """Sana tanlashda kulrang ko'rinadigan band kunlar."""

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
