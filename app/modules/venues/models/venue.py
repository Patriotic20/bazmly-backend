from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class VenueStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    CLOSED = "closed"


class Venue(IdIntPk, TimestampMixin, Base):
    """A branch. The brand above it is a `venue_group`.

    `status` is administrative and persistent — `status = 'closed'` is not the same
    as being shut for the night. Open-right-now is computed from
    `venue_working_hours` plus the clock and is never stored.

    `venue_type` is one value per branch, held here rather than in a
    `venue_venue_types` join against a `venue_types` lookup table. Two values that
    never change do not need two tables, and a branch that is both a restaurant
    and a wedding hall was a shape nothing in the product ever read.

    No `logo_url` here: the logo belongs to the group.
    """

    __tablename__ = "venues"
    __table_args__ = (
        Index(
            "ix_venues_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index("ix_venues_location", "location", postgresql_using="gist"),
        Index("ix_venues_venue_group_id_status", "venue_group_id", "status"),
        CheckConstraint(
            "status IN ('draft', 'pending', 'active', 'blocked', 'closed')",
            name="ck_venues_status",
        ),
        # The values are spelled out rather than derived from `VenueTypeSlug`:
        # `app.modules.venues.enums` imports this module, so importing it back
        # here would be circular. The enum guards the Pydantic layer instead.
        CheckConstraint(
            "venue_type IN ('restoran', 'toyxona')",
            name="ck_venues_venue_type",
        ),
    )

    venue_group_id: Mapped[int] = mapped_column(ForeignKey("venue_groups.id"), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    manager_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), nullable=False)
    venue_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    street: Mapped[str] = mapped_column(String(255), nullable=False)
    house_number: Mapped[str] = mapped_column(String(50), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    location: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    total_seats: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capacity_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capacity_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="UZS", nullable=False)
    min_advance_booking_days: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    late_grace_minutes: Mapped[int] = mapped_column(SmallInteger, default=40, nullable=False)
    requires_deposit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deposit_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    rating_avg: Mapped[Decimal] = mapped_column(Numeric(2, 1), default=0, nullable=False)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=VenueStatus.DRAFT, nullable=False)
    onboarding_step: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tagline: Mapped[str | None] = mapped_column(String(120), nullable=True)
