from typing import Any


class AppError(Exception):
    """Base class for every application-level error.

    Carries the HTTP status code, a stable machine-readable ``code``, a human
    readable ``message`` and optional structured ``details``.
    """

    status_code: int = 500
    code: str = "internal_error"
    message: str = "Serverda xatolik yuz berdi"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message if message is not None else type(self).message
        self.code = code if code is not None else type(self).code
        self.status_code = status_code if status_code is not None else type(self).status_code
        self.details: dict[str, Any] | None = details
        super().__init__(self.message)


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"
    message = "So'rov noto'g'ri"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Avtorizatsiya talab qilinadi"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message = "Ruxsat yo'q"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "Ziddiyat yuz berdi"


class DomainError(Exception):
    """Base for every business-rule failure.

    There is deliberately only one `NotFoundError` and it lives here, not in the
    `AppError` family: a service raising "no such booking" and a repository
    raising "this dish is not on that branch's menu" are the same fact, and two
    classes with one name would be resolved by import order.

    Separate from `AppError` on purpose: `AppError` is HTTP-shaped and carries a
    status code, while a domain error describes what the business refused and
    lets `handlers.py` decide the status. Services raise these; they never import
    FastAPI and never choose a status code.
    """

    code: str = "domain_error"
    message: str = "So'rovni bajarib bo'lmadi"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message if message is not None else type(self).message
        self.code = type(self).code
        self.details: dict[str, Any] | None = details
        super().__init__(self.message)


# --- generic ---------------------------------------------------------------


class NotFoundError(DomainError):
    code = "not_found"
    message = "Ma'lumot topilmadi"


class PermissionDeniedError(DomainError):
    code = "permission_denied"
    message = "Bu amalni bajarishga ruxsatingiz yo'q"


class ValidationFailedError(DomainError):
    code = "validation_failed"
    message = "So'rov to'g'ri emas"


# --- registration and identity ---------------------------------------------


class PhoneAlreadyRegisteredError(DomainError):
    code = "phone_already_registered"
    message = "Bu telefon raqami allaqachon ro'yxatda"


class InvalidCodeError(DomainError):
    code = "invalid_code"
    message = "Tasdiqlash kodi noto'g'ri"


class CodeExpiredError(DomainError):
    code = "code_expired"
    message = "Tasdiqlash kodi muddati tugagan"


class TooManyAttemptsError(DomainError):
    code = "too_many_attempts"
    message = "Urinishlar juda ko'p. Keyinroq urinib ko'ring"


# --- booking ----------------------------------------------------------------


class TableAlreadyBookedError(DomainError):
    code = "table_already_booked"
    message = "Bu stol shu vaqtga allaqachon band"


class VenueAlreadyBookedError(DomainError):
    code = "venue_already_booked"
    message = "Bu muassasa o'sha kunga allaqachon band"


class VenueClosedError(DomainError):
    code = "venue_closed"
    message = "Muassasa o'sha vaqtda yopiq"


class LeadTimeTooShortError(DomainError):
    code = "lead_time_too_short"
    message = "Bu muassasa bronni oldinroq talab qiladi"


class CapacityExceededError(DomainError):
    code = "capacity_exceeded"
    message = "Bu mehmonlar soni uchun joy mos kelmaydi"


class DepositRequiredError(DomainError):
    code = "deposit_required"
    message = "Bu bronni tasdiqlash uchun oldindan to'lov talab qilinadi"


class BookingNotCheckInableError(DomainError):
    code = "booking_not_check_inable"
    message = "Bu bronni qayd etib bo'lmaydi"


# --- orders -----------------------------------------------------------------


class TableHasOpenOrderError(DomainError):
    code = "table_has_open_order"
    message = "Bu stolda allaqachon ochiq chek bor"


class PaymentIncompleteError(DomainError):
    code = "payment_incomplete"
    message = "Chek to'liq to'lanmagan"


class ReceiptAlreadyIssuedError(DomainError):
    code = "receipt_already_issued"
    message = "Bu buyurtma uchun chek allaqachon chiqarilgan"


# --- promotions and reviews -------------------------------------------------


class PromoCodeInvalidError(DomainError):
    code = "promo_code_invalid"
    message = "Bu promokoddan foydalanib bo'lmaydi"


class PromoCodeExhaustedError(DomainError):
    code = "promo_code_exhausted"
    message = "Bu promokod to'liq ishlatilgan"


class AlreadyReviewedError(DomainError):
    code = "already_reviewed"
    message = "Bu bronga allaqachon sharh qoldirilgan"
