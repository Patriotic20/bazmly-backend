from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class ServiceCatalog(IdIntPk, TimestampMixin, Base):
    """A closed, platform-owned list, because the onboarding screen offers one.

    If owners are later allowed free-text services, add `venue_services.custom_name`
    rather than letting them write into the catalog.

    `applies_to_venue_type` was a foreign key into `venue_types`. That table is
    gone, so the slug is held here directly; NULL still means "suits any venue".
    """

    __tablename__ = "service_catalog"
    __table_args__ = (
        # Spelled out rather than derived from `VenueTypeSlug`: a model may not
        # import another module's model file, and the enum lives beside `Venue`.
        CheckConstraint(
            "applies_to_venue_type IS NULL OR applies_to_venue_type IN ('restoran', 'toyxona')",
            name="ck_service_catalog_applies_to_venue_type",
        ),
    )

    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    icon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    applies_to_venue_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
