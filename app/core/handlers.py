import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    AlreadyReviewedError,
    AppError,
    BookingNotCheckInableError,
    CapacityExceededError,
    CodeExpiredError,
    DepositRequiredError,
    DomainError,
    InvalidCodeError,
    LeadTimeTooShortError,
    NotFoundError,
    PaymentIncompleteError,
    PermissionDeniedError,
    PhoneAlreadyRegisteredError,
    PromoCodeExhaustedError,
    PromoCodeInvalidError,
    ReceiptAlreadyIssuedError,
    TableAlreadyBookedError,
    TableHasOpenOrderError,
    TooManyAttemptsError,
    ValidationFailedError,
    VenueAlreadyBookedError,
    VenueClosedError,
)
from app.core.middleware.request_id import get_request_id

logger = logging.getLogger("app.error")

# Domain errors carry no status code — deciding the HTTP shape is this layer's job,
# which is what lets services stay free of FastAPI.
DOMAIN_STATUS: dict[type[DomainError], int] = {
    NotFoundError: 404,
    PermissionDeniedError: 403,
    # 409: the request was well-formed but lost a race or hit a live-state rule.
    PhoneAlreadyRegisteredError: 409,
    TableAlreadyBookedError: 409,
    VenueAlreadyBookedError: 409,
    TableHasOpenOrderError: 409,
    ReceiptAlreadyIssuedError: 409,
    AlreadyReviewedError: 409,
    # 429: throttles.
    TooManyAttemptsError: 429,
    # 422: the request is understood but the business refuses it.
    ValidationFailedError: 422,
    InvalidCodeError: 422,
    CodeExpiredError: 422,
    VenueClosedError: 422,
    LeadTimeTooShortError: 422,
    CapacityExceededError: 422,
    DepositRequiredError: 422,
    PaymentIncompleteError: 422,
    BookingNotCheckInableError: 422,
    PromoCodeInvalidError: 422,
    PromoCodeExhaustedError: 422,
}

DEFAULT_DOMAIN_STATUS = 422


def status_for(error: DomainError) -> int:
    """Exact class first, then the nearest mapped base.

    A new domain error added without a mapping lands on 422 rather than 500 — the
    business refused it, which is a client-visible outcome, not a server fault.
    """
    exact = DOMAIN_STATUS.get(type(error))
    if exact is not None:
        return exact
    for klass in type(error).__mro__:
        if klass in DOMAIN_STATUS:
            return DOMAIN_STATUS[klass]
    return DEFAULT_DOMAIN_STATUS


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """The single error body every handler returns.

    Flat rather than wrapped in `{"error": {...}}`: the mobile team generates
    clients from the schema, and one level of nesting per error is one more thing
    every call site has to unwrap correctly.
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": get_request_id(),
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register every application exception handler on ``app``."""

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, DomainError)
        return error_response(status_for(exc), exc.code, exc.message, exc.details)

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, AppError)
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        return error_response(
            status_code=422,
            code="validation_error",
            message="Request validation failed",
            details={"errors": jsonable_errors(exc)},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        return error_response(
            status_code=exc.status_code,
            code="http_error",
            message=str(exc.detail),
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, exc: Exception) -> JSONResponse:
        logger.warning("Database integrity error on %s %s", request.method, request.url.path)
        return error_response(
            status_code=409,
            code="integrity_error",
            message="The request conflicts with the current state of the database",
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled error on %s %s (request_id=%s)",
            request.method,
            request.url.path,
            get_request_id(),
        )
        return error_response(
            status_code=500,
            code="internal_error",
            message="Internal server error",
        )


def jsonable_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Strip non-serializable payloads out of pydantic validation errors."""
    cleaned: list[dict[str, Any]] = []
    for error in exc.errors():
        item = dict(error)
        item.pop("ctx", None)
        item.pop("input", None)
        item["loc"] = [str(part) for part in item.get("loc", ())]
        cleaned.append(item)
    return cleaned
