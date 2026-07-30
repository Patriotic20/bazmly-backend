from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column


def utcnow_naive() -> datetime:
    """Current UTC time as a naive datetime (UTC+00:00, tzinfo stripped)."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_naive_utc(dt: datetime | None) -> datetime | None:
    """Convert a tz-aware datetime to naive UTC.

    Passes None and already-naive datetimes through unchanged.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


class IdIntPk:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=utcnow_naive,
        server_default=func.timezone("UTC", func.now()),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=utcnow_naive,
        onupdate=utcnow_naive,
        server_default=func.timezone("UTC", func.now()),
        nullable=False,
    )
