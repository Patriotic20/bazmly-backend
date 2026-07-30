from typing import Any


class AppError(Exception):
    """Base class for every application-level error.

    Carries the HTTP status code, a stable machine-readable ``code``, a human
    readable ``message`` and optional structured ``details``.
    """

    status_code: int = 500
    code: str = "internal_error"
    message: str = "Internal server error"

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
    message = "Bad request"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message = "Forbidden"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "Conflict"


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
    message: str = "Request could not be completed"

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
    message = "Resource not found"


class PermissionDeniedError(DomainError):
    code = "permission_denied"
    message = "You do not have permission to do that"


class ValidationFailedError(DomainError):
    code = "validation_failed"
    message = "The request is not valid"


# --- registration and identity ---------------------------------------------


class PhoneAlreadyRegisteredError(DomainError):
    code = "phone_already_registered"
    message = "That phone number is already registered"


class InvalidCodeError(DomainError):
    code = "invalid_code"
    message = "The confirmation code is incorrect"


class CodeExpiredError(DomainError):
    code = "code_expired"
    message = "The confirmation code has expired"


class TooManyAttemptsError(DomainError):
    code = "too_many_attempts"
    message = "Too many attempts. Try again later"


# --- booking ----------------------------------------------------------------


class TableAlreadyBookedError(DomainError):
    code = "table_already_booked"
    message = "That table is already booked for this time"


class VenueAlreadyBookedError(DomainError):
    code = "venue_already_booked"
    message = "This venue is already booked for that day"


class VenueClosedError(DomainError):
    code = "venue_closed"
    message = "The venue is closed at that time"


class LeadTimeTooShortError(DomainError):
    code = "lead_time_too_short"
    message = "This venue needs more notice for a booking"


class CapacityExceededError(DomainError):
    code = "capacity_exceeded"
    message = "That party size does not fit"


class DepositRequiredError(DomainError):
    code = "deposit_required"
    message = "A deposit is required to confirm this booking"


class BookingNotCheckInableError(DomainError):
    code = "booking_not_check_inable"
    message = "This booking cannot be checked in"


# --- orders -----------------------------------------------------------------


class TableHasOpenOrderError(DomainError):
    code = "table_has_open_order"
    message = "That table already has an open check"


class PaymentIncompleteError(DomainError):
    code = "payment_incomplete"
    message = "The check is not fully paid"


class ReceiptAlreadyIssuedError(DomainError):
    code = "receipt_already_issued"
    message = "A receipt has already been issued for this order"


# --- promotions and reviews -------------------------------------------------


class PromoCodeInvalidError(DomainError):
    code = "promo_code_invalid"
    message = "That promo code cannot be used"


class PromoCodeExhaustedError(DomainError):
    code = "promo_code_exhausted"
    message = "That promo code has been fully used"


class AlreadyReviewedError(DomainError):
    code = "already_reviewed"
    message = "This booking has already been reviewed"
