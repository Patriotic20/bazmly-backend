from collections.abc import Sequence
from datetime import date as date_type
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_availability_cache, venue_availability_prefix
from app.core.database.mixins import utcnow_naive
from app.core.exceptions import (
    BookingNotCheckInableError,
    CapacityExceededError,
    LeadTimeTooShortError,
    NotFoundError,
    PermissionDeniedError,
    TableAlreadyBookedError,
    ValidationFailedError,
    VenueClosedError,
)
from app.core.integrity import translate_integrity_error
from app.core.security import generate_token
from app.modules.bookings.enums import BookingKind, BookingStatus, PriceLineType
from app.modules.bookings.models import (
    Booking,
    BookingItem,
    BookingPriceLine,
)
from app.modules.bookings.models import (
    BookingService as BookingServiceRow,
)
from app.modules.bookings.repositories import BookingRepository
from app.modules.bookings.schemas import (
    BookingCancel,
    BookingItemCreate,
    BookingItemRead,
    BookingListItem,
    BookingOwnerDetail,
    BookingRead,
    BookingServiceCreate,
    BookingServiceRead,
    HallEventCreate,
    PriceLineRead,
    SeatedSummary,
    TableReservationCreate,
)
from app.modules.menu.models import MenuItem
from app.modules.menu.repositories import MenuItemRepository
from app.modules.services.repositories import VenueServiceRepository
from app.modules.staff.repositories import VenueStaffRepository
from app.modules.venues.models import Venue
from app.modules.venues.repositories import (
    VenueGuestTierRepository,
    VenueRepository,
    VenueTableRepository,
)

MONEY = Decimal("0.01")
PERCENT = Decimal("100")

TICKET_CODE_LENGTH = 12
QR_TOKEN_LENGTH = 24


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


class BookingService:
    """Restaurant reservations and to'yxona hall events.

    Guards run in a fixed order before anything is written — lead time, then the
    venue's opening hours, then capacity — so the caller gets the most specific
    reason for a refusal rather than whichever check happened to run first.

    Double booking is settled in Postgres. The overlap pre-check exists only to
    produce a readable message; the exclusion constraint remains the authority,
    and its `IntegrityError` is translated rather than allowed to escape.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.bookings = BookingRepository(session)
        self.venues = VenueRepository(session)
        self.tables = VenueTableRepository(session)
        self.tiers = VenueGuestTierRepository(session)
        self.venue_services = VenueServiceRepository(session)
        self.menu_items = MenuItemRepository(session)
        self.staff = VenueStaffRepository(session)

    async def create_table_reservation(
        self, user_id: int, payload: TableReservationCreate
    ) -> BookingOwnerDetail:
        venue = await self._require_venue(payload.venue_id)
        await self._guard_lead_time(venue, payload.booking_date)
        await self._guard_open(venue.id, payload.booking_date, payload.start_time)

        table = await self.tables.get_by_id(payload.table_id)
        if table is None or table.venue_id != venue.id:
            raise NotFoundError("Bu stol ushbu muassasaga tegishli emas")
        if table.seats < payload.guests_count:
            raise CapacityExceededError(
                f"{table.number}-stol {table.seats} o'rinlik, {payload.guests_count} emas"
            )

        overlapping = await self.bookings.find_overlapping(
            table.id, payload.booking_date, payload.start_time, payload.end_time
        )
        if overlapping:
            raise TableAlreadyBookedError(
                f"{table.number}-stol {payload.start_time:%H:%M} va "
                f"{payload.end_time:%H:%M} oralig'ida allaqachon band"
            )

        items, menu_subtotal = await self._build_items_in_transaction(venue.id, payload.items)
        service_rows, services_total = await self._build_services_in_transaction(payload.services)
        quote = self._assemble_price(
            venue_deposit_percent=venue.deposit_percent if venue.requires_deposit else None,
            base_amount=menu_subtotal,
            base_label="Menyu",
            base_line_type=PriceLineType.CATERING,
            services_total=services_total,
            service_rows=service_rows,
            currency=venue.currency,
        )

        booking = Booking(
            user_id=user_id,
            venue_id=venue.id,
            kind=BookingKind.TABLE_RESERVATION,
            booking_date=payload.booking_date,
            start_time=payload.start_time,
            end_time=payload.end_time,
            guests_count=payload.guests_count,
            status=BookingStatus.PENDING,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            note=payload.note,
            subtotal=quote.subtotal,
            deposit_amount=quote.deposit,
            total_amount=quote.total,
            currency=venue.currency,
            receipt_number=generate_token(8),
            ticket_code=generate_token(8)[:TICKET_CODE_LENGTH],
            qr_token=generate_token(16)[:QR_TOKEN_LENGTH],
            auto_cancel_at=self._auto_cancel_at(
                payload.booking_date, payload.start_time, venue.late_grace_minutes
            ),
            table_id=table.id,
        )

        try:
            created = await self.bookings.create_table_reservation(booking)
            await self.bookings.add_items(created.id, items)
            await self.bookings.add_services(created.id, service_rows)
            await self.bookings.add_price_lines(created.id, quote.lines)
            await self.bookings.record_status_change(
                created.id, None, BookingStatus.PENDING, changed_by_user_id=user_id
            )
            await self.session.commit()
        except IntegrityError as error:
            raise translate_integrity_error(error) from error

        await get_availability_cache().invalidate(venue_availability_prefix(venue.id))
        return await self._detail_in_transaction(created, venue_name=None)

    async def create_hall_event(self, user_id: int, payload: HallEventCreate) -> BookingOwnerDetail:
        venue = await self._require_venue(payload.venue_id)
        await self._guard_lead_time(venue, payload.booking_date)
        await self._guard_open(venue.id, payload.booking_date, payload.start_time)

        tier = await self.tiers.get_for_guest_count(venue.id, payload.guests_count)
        if tier is None:
            raise CapacityExceededError(
                f"{payload.guests_count} mehmon uchun bu muassasada narx bosqichi yo'q"
            )

        service_rows, services_total = await self._build_services_in_transaction(payload.services)
        quote = self._assemble_price(
            venue_deposit_percent=venue.deposit_percent if venue.requires_deposit else None,
            base_amount=_money(tier.base_price),
            base_label="Zal ijarasi",
            base_line_type=PriceLineType.HALL_RENTAL,
            services_total=services_total,
            service_rows=service_rows,
            currency=venue.currency,
        )

        booking = Booking(
            user_id=user_id,
            venue_id=venue.id,
            kind=BookingKind.HALL_EVENT,
            booking_date=payload.booking_date,
            start_time=payload.start_time,
            end_time=payload.end_time,
            guests_count=payload.guests_count,
            status=BookingStatus.PENDING,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            note=payload.note,
            subtotal=quote.subtotal,
            deposit_amount=quote.deposit,
            total_amount=quote.total,
            currency=venue.currency,
            receipt_number=generate_token(8),
            ticket_code=generate_token(8)[:TICKET_CODE_LENGTH],
            qr_token=generate_token(16)[:QR_TOKEN_LENGTH],
            auto_cancel_at=self._auto_cancel_at(
                payload.booking_date, payload.start_time, venue.late_grace_minutes
            ),
            guest_tier_id=tier.id,
        )

        try:
            created = await self.bookings.create_hall_event(booking)
            await self.bookings.add_services(created.id, service_rows)
            await self.bookings.add_price_lines(created.id, quote.lines)
            await self.bookings.record_status_change(
                created.id, None, BookingStatus.PENDING, changed_by_user_id=user_id
            )
            await self.session.commit()
        except IntegrityError as error:
            raise translate_integrity_error(error) from error

        await get_availability_cache().invalidate(venue_availability_prefix(venue.id))
        return await self._detail_in_transaction(created, venue_name=None)

    async def list_for_user(
        self, user_id: int, statuses: Sequence[str] | None = None
    ) -> Sequence[BookingListItem]:
        rows = await self.bookings.list_for_user(user_id, statuses)
        return [
            BookingListItem(
                id=row.booking.id,
                venue_id=row.venue.id,
                venue_name=row.venue_name,
                kind=BookingKind(row.booking.kind),
                status=BookingStatus(row.booking.status),
                booking_date=row.booking.booking_date,
                start_time=row.booking.start_time,
                end_time=row.booking.end_time,
                guests_count=row.booking.guests_count,
                total_amount=row.booking.total_amount,
                currency=row.booking.currency,
                table_number=row.table.number if row.table is not None else None,
            )
            for row in rows
        ]

    async def get_detail(self, user_id: int, booking_id: int) -> BookingOwnerDetail:
        """The owner's own booking. The only place `qr_token` is returned."""
        booking = await self.bookings.get_by_id(booking_id)
        if booking is None:
            raise NotFoundError("Bron topilmadi")
        if booking.user_id != user_id:
            raise PermissionDeniedError("Bu bron boshqa foydalanuvchiga tegishli")
        return await self._detail_in_transaction(booking, venue_name=None)

    async def venue_day(
        self, venue_id: int, day: date_type, statuses: Sequence[str] | None = None
    ) -> Sequence[BookingRead]:
        rows = await self.bookings.list_for_venue_day(venue_id, day, statuses)
        return [BookingRead.model_validate(row) for row in rows]

    async def cancel(self, user_id: int, booking_id: int, payload: BookingCancel) -> BookingRead:
        """Inside the deposit window the deposit is forfeited; outside it a refund
        is queued. Either way the decision is recorded in the status history, so
        the reason a guest was or was not refunded is auditable later.
        """
        now = utcnow_naive()
        booking = await self.bookings.get_by_id(booking_id)
        if booking is None:
            raise NotFoundError("Bron topilmadi")
        if booking.user_id != user_id:
            raise PermissionDeniedError("Bu bron boshqa foydalanuvchiga tegishli")
        if booking.status in (BookingStatus.CANCELLED, BookingStatus.COMPLETED):
            raise BookingNotCheckInableError("Bu bronni endi bekor qilib bo'lmaydi")

        forfeited = self._deposit_is_forfeited(booking, now)
        comment = payload.reason or ("Deposit forfeited" if forfeited else "Deposit refundable")
        updated = await self.bookings.set_status(
            booking_id, BookingStatus.CANCELLED, now, reason=payload.reason
        )
        if updated is None:
            raise NotFoundError("Bron topilmadi")
        await self.bookings.record_status_change(
            booking_id,
            booking.status,
            BookingStatus.CANCELLED,
            changed_by_user_id=user_id,
            comment=comment,
        )
        await self.session.commit()
        await get_availability_cache().invalidate(venue_availability_prefix(booking.venue_id))
        return BookingRead.model_validate(updated)

    async def confirm(self, staff_user_id: int, venue_id: int, booking_id: int) -> BookingRead:
        """The branch accepting a request.

        Nothing else in the system produces a `confirmed` booking, and
        `check_in_by_qr` refuses anything that is not confirmed — so until this
        runs, a guest's ticket can never be scanned.
        """
        return await self._decide(
            staff_user_id,
            venue_id,
            booking_id,
            BookingStatus.CONFIRMED,
            comment="Confirmed by venue",
        )

    async def reject(
        self, staff_user_id: int, venue_id: int, booking_id: int, payload: BookingCancel
    ) -> BookingRead:
        """The branch refusing a request.

        The booking lands in `cancelled`, the same state a guest's own
        cancellation produces — one terminal state rather than two, so every
        read already handles it. Who ended it is in the status history.
        """
        return await self._decide(
            staff_user_id,
            venue_id,
            booking_id,
            BookingStatus.CANCELLED,
            comment=payload.reason or "Rejected by venue",
            reason=payload.reason,
        )

    async def check_in_by_qr(self, staff_user_id: int, venue_id: int, qr_token: str) -> BookingRead:
        """Scanned by the venue, from the token the guest shows.

        Three separate refusals, in order: the token must exist, the scanner must
        actually work at that branch, and the booking must be `confirmed`. A second
        scan fails the third check, which is what makes the token single-use.
        """
        now = utcnow_naive()
        booking = await self.bookings.get_by_qr_token(qr_token)
        if booking is None or booking.venue_id != venue_id:
            raise NotFoundError("Bu chipta ushbu muassasaga tegishli emas")

        if not await self._staff_works_at(staff_user_id, booking.venue_id):
            raise PermissionDeniedError("Siz bu muassasada ishlamaysiz")

        updated = await self.bookings.check_in(booking.id, staff_user_id, now)
        if updated is None:
            raise BookingNotCheckInableError("Bu bron tasdiqlanmagan yoki allaqachon qayd etilgan")
        await self.session.commit()
        return BookingRead.model_validate(updated)

    async def check_out(self, staff_user_id: int, venue_id: int, booking_id: int) -> SeatedSummary:
        """Writes `seated_minutes` once, in whole minutes."""
        now = utcnow_naive()
        booking = await self.bookings.get_by_id(booking_id)
        if booking is None or booking.venue_id != venue_id:
            raise NotFoundError("Bu muassasada bunday bron topilmadi")
        if not await self._staff_works_at(staff_user_id, venue_id):
            raise PermissionDeniedError("Siz bu muassasada ishlamaysiz")

        updated = await self.bookings.check_out(booking_id, now)
        if updated is None:
            raise BookingNotCheckInableError("Bu bron qayd etilmagan")
        await self.bookings.record_status_change(
            booking_id,
            BookingStatus.CHECKED_IN,
            BookingStatus.COMPLETED,
            changed_by_user_id=staff_user_id,
        )
        await self.session.commit()
        return SeatedSummary(
            booking_id=updated.id,
            checked_in_at=updated.checked_in_at,
            checked_out_at=updated.checked_out_at,
            seated_minutes=updated.seated_minutes,
        )

    async def expire_stale(self) -> Sequence[int]:
        """Confirmed bookings past their grace window become no-shows."""
        ids = await self.bookings.expire_stale(utcnow_naive())
        await self.session.commit()
        return ids

    # --- internals -----------------------------------------------------------

    async def _require_venue(self, venue_id: int) -> Venue:
        venue = await self.venues.get_by_id(venue_id)
        if venue is None:
            raise NotFoundError("Muassasa topilmadi")
        return venue

    async def _guard_lead_time(self, venue: Venue, booking_date: date_type) -> None:
        """`min_advance_booking_days` is the venue's notice period, not a courtesy."""
        required = venue.min_advance_booking_days
        days_ahead = (booking_date - utcnow_naive().date()).days
        if days_ahead < required:
            raise LeadTimeTooShortError(
                f"Bu muassasa kamida {required} kun oldin bron qilishni talab qiladi",
                details={"required_days": required, "given_days": days_ahead},
            )

    async def _guard_open(self, venue_id: int, booking_date: date_type, start_time: time) -> None:
        """Working hours with a special-day override, evaluated in the database."""
        local_dt = datetime.combine(booking_date, start_time)
        if not await self.venues.is_open_at(venue_id, local_dt):
            raise VenueClosedError("Muassasa o'sha vaqtda yopiq")

    async def _decide(
        self,
        staff_user_id: int,
        venue_id: int,
        booking_id: int,
        status: str,
        *,
        comment: str,
        reason: str | None = None,
    ) -> BookingRead:
        """Accept or refuse a pending request, in one place.

        The three refusals are ordered the way `check_in_by_qr` orders its own:
        the booking must belong to this branch, the caller must work there, and
        only then does its state matter. Reversing the last two would tell a
        stranger whether a booking is still open.
        """
        now = utcnow_naive()
        booking = await self.bookings.get_by_id(booking_id)
        if booking is None or booking.venue_id != venue_id:
            raise NotFoundError("Bu muassasada bunday bron topilmadi")
        if not await self._staff_works_at(staff_user_id, venue_id):
            raise PermissionDeniedError("Siz bu muassasada ishlamaysiz")
        if booking.status != BookingStatus.PENDING:
            raise ValidationFailedError(
                "Bu bron allaqachon ko'rib chiqilgan",
                details={"status": booking.status},
            )

        updated = await self.bookings.set_status(booking_id, status, now, reason=reason)
        if updated is None:
            raise NotFoundError("Bron topilmadi")
        await self.bookings.record_status_change(
            booking_id,
            BookingStatus.PENDING,
            status,
            changed_by_user_id=staff_user_id,
            comment=comment,
        )
        await self.session.commit()
        # A refusal frees the table or the day it was holding; a confirmation
        # does not, but the cached slot list keys on neither status.
        await get_availability_cache().invalidate(venue_availability_prefix(booking.venue_id))
        return BookingRead.model_validate(updated)

    async def _staff_works_at(self, user_id: int, venue_id: int) -> bool:
        rows = await self.staff.list_for_user(user_id)
        return any(row.venue_id in (venue_id, None) for row in rows)

    def _auto_cancel_at(
        self, booking_date: date_type, start_time: time, grace_minutes: int
    ) -> datetime:
        return datetime.combine(booking_date, start_time) + timedelta(minutes=grace_minutes)

    def _deposit_is_forfeited(self, booking: Booking, now: datetime) -> bool:
        """Inside 24 hours of the start, a paid deposit is not returned."""
        if booking.deposit_paid_at is None or booking.deposit_amount <= 0:
            return False
        start = datetime.combine(booking.booking_date, booking.start_time)
        return (start - now) < timedelta(hours=24)

    async def _build_items_in_transaction(
        self, venue_id: int, requested: Sequence[BookingItemCreate]
    ) -> tuple[list[BookingItem], Decimal]:
        """Snapshot price and name on every line, at this branch's price.

        `resolve_price` raises when the branch has no `menu_item_branches` row, so
        a dish that branch does not serve cannot be pre-ordered at the chain's
        catalogue price.
        """
        items: list[BookingItem] = []
        subtotal = Decimal("0")
        for entry in requested:
            unit_price = await self.menu_items.resolve_price(entry.menu_item_id, venue_id)
            name = await self._menu_item_name(entry.menu_item_id, venue_id)
            total = _money(unit_price * entry.quantity)
            subtotal += total
            items.append(
                BookingItem(
                    menu_item_id=entry.menu_item_id,
                    quantity=entry.quantity,
                    unit_price=_money(unit_price),
                    total_price=total,
                    name_snapshot=name,
                )
            )
        return items, _money(subtotal)

    async def _menu_item_name(self, menu_item_id: int, venue_id: int) -> str:
        detail = await self.menu_items.get_with_variants(menu_item_id, venue_id)
        if detail is not None:
            return detail.name
        item: MenuItem | None = await self.menu_items.get_by_id(menu_item_id)
        if item is None:
            raise NotFoundError("Taom topilmadi")
        return f"#{item.id}"

    async def _build_services_in_transaction(
        self, requested: Sequence[BookingServiceCreate]
    ) -> tuple[list[BookingServiceRow], Decimal]:
        rows: list[BookingServiceRow] = []
        total = Decimal("0")
        for entry in requested:
            service = await self.venue_services.get_by_id(entry.venue_service_id)
            if service is None:
                raise NotFoundError("Xizmat topilmadi")
            detail = await self.venue_services.get_with_items(service.id)
            name = f"#{service.id}" if detail is None else f"#{service.service_catalog_id}"
            line_total = _money(service.price * entry.quantity)
            total += line_total
            rows.append(
                BookingServiceRow(
                    venue_service_id=service.id,
                    quantity=entry.quantity,
                    unit_price=_money(service.price),
                    name_snapshot=name,
                    total_price=line_total,
                )
            )
        return rows, _money(total)

    def _assemble_price(
        self,
        *,
        venue_deposit_percent: Decimal | None,
        base_amount: Decimal,
        base_label: str,
        base_line_type: str,
        services_total: Decimal,
        service_rows: Sequence[BookingServiceRow],
        currency: str,
    ) -> _Quote:
        """Base → services → subtotal → total → deposit, with one frozen price line
        per component.

        Nothing reduces the price between subtotal and total, so the two are equal
        by construction. Both are still carried, because the booking row stores both
        and a receipt that showed only one number would hide the breakdown.

        The deposit is **subtracted** from the total, not added: it is a portion of
        the price paid up front, so adding it would charge the guest twice for the
        same money. Its line is therefore negative and, unlike the others, does not
        participate in the sum that produces the total.
        """
        lines: list[BookingPriceLine] = []
        order = 0

        if base_amount > 0:
            lines.append(
                BookingPriceLine(
                    sort_order=order,
                    line_type=base_line_type,
                    label_snapshot=base_label,
                    unit_price=base_amount,
                    quantity=1,
                    amount=base_amount,
                )
            )
            order += 1

        for row in service_rows:
            lines.append(
                BookingPriceLine(
                    sort_order=order,
                    line_type=PriceLineType.SERVICE_LOGISTICS,
                    label_snapshot=row.name_snapshot,
                    unit_price=row.unit_price,
                    quantity=row.quantity,
                    amount=row.total_price,
                )
            )
            order += 1

        subtotal = _money(base_amount + services_total)
        total = subtotal

        deposit = Decimal("0")
        if venue_deposit_percent is not None and venue_deposit_percent > 0:
            deposit = _money(total * venue_deposit_percent / PERCENT)
            lines.append(
                BookingPriceLine(
                    sort_order=order,
                    line_type=PriceLineType.DEPOSIT,
                    label_snapshot="Depozit",
                    unit_price=deposit,
                    quantity=1,
                    amount=-deposit,
                )
            )

        return _Quote(
            subtotal=subtotal,
            deposit=deposit,
            total=total,
            currency=currency,
            lines=lines,
        )

    async def _detail_in_transaction(
        self, booking: Booking, venue_name: str | None
    ) -> BookingOwnerDetail:
        items = await self.bookings.list_items(booking.id)
        services = await self.bookings.list_services(booking.id)
        lines = await self.bookings.list_price_lines(booking.id)
        return BookingOwnerDetail(
            booking=BookingRead.model_validate(booking),
            qr_token=booking.qr_token,
            venue_name=venue_name or "",
            items=[BookingItemRead.model_validate(item) for item in items],
            services=[BookingServiceRead.model_validate(row) for row in services],
            price_lines=[PriceLineRead.model_validate(line) for line in lines],
        )


class _Quote:
    """The assembled price, before it is written onto the booking."""

    def __init__(
        self,
        *,
        subtotal: Decimal,
        deposit: Decimal,
        total: Decimal,
        currency: str,
        lines: list[BookingPriceLine],
    ) -> None:
        self.subtotal = subtotal
        self.deposit = deposit
        self.total = total
        self.currency = currency
        self.lines = lines
