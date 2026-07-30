from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class ServicePriceUnit(StrEnum):
    FLAT = "flat"
    PER_GUEST = "per_guest"
    PER_HOUR = "per_hour"


class VenueService(IdIntPk, TimestampMixin, Base):
    """What a chain or branch charges for a catalog service.

    `venue_id IS NULL` means the price applies across the whole chain. This is the
    single writable source for the dasturxon — the customer-facing package view is
    derived from it, which is why there are no `catering_packages`.
    """

    __tablename__ = "venue_services"
    __table_args__ = (
        CheckConstraint(
            "price_unit IN ('flat', 'per_guest', 'per_hour')",
            name="ck_venue_services_price_unit",
        ),
    )

    venue_group_id: Mapped[int] = mapped_column(
        ForeignKey("venue_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    venue_id: Mapped[int | None] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=True
    )
    service_catalog_id: Mapped[int] = mapped_column(
        ForeignKey("service_catalog.id"), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="UZS", nullable=False)
    price_unit: Mapped[str] = mapped_column(
        String(20), default=ServicePriceUnit.FLAT, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
