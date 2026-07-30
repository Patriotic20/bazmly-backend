"""Constraint name to domain error.

Matching on the constraint name, never on the message text: Postgres message
wording is not a stable API, varies by locale and version, and "duplicate key
value violates unique constraint" is the same sentence for every unique index in
the schema. The name is the only part that identifies which rule was broken.
"""

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    DomainError,
    PhoneAlreadyRegisteredError,
    TableAlreadyBookedError,
    TableHasOpenOrderError,
    ValidationFailedError,
    VenueAlreadyBookedError,
)

CONSTRAINT_ERRORS: dict[str, type[DomainError]] = {
    "no_overlapping_table_bookings": TableAlreadyBookedError,
    "one_hall_event_per_day": VenueAlreadyBookedError,
    "one_open_order_per_table": TableHasOpenOrderError,
    # Postgres generated `users_phone_key` from the column's `unique=True`.
    # `uq_users_phone` is kept so a future rename does not silently stop matching.
    "users_phone_key": PhoneAlreadyRegisteredError,
    "uq_users_phone": PhoneAlreadyRegisteredError,
}


def constraint_name(error: IntegrityError) -> str | None:
    """The violated constraint, from asyncpg's structured error fields."""
    original = getattr(error, "orig", None)
    cause = getattr(original, "__cause__", None)
    for candidate in (original, cause):
        name = getattr(candidate, "constraint_name", None)
        if isinstance(name, str) and name:
            return name
    return None


def translate_integrity_error(error: IntegrityError) -> DomainError:
    """Map a constraint violation onto the rule it broke.

    An unmapped constraint becomes `ValidationFailedError` carrying the name, so a
    new constraint surfaces as a 422 naming itself rather than a 500 that hides
    which invariant fired.
    """
    name = constraint_name(error)
    if name is not None and name in CONSTRAINT_ERRORS:
        return CONSTRAINT_ERRORS[name]()
    return ValidationFailedError(
        "So'rov mavjud ma'lumotlarga to'g'ri kelmaydi",
        details={"constraint": name} if name else None,
    )
