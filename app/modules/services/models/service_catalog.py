from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class ServiceCatalog(IdIntPk, TimestampMixin, Base):
    """A closed, platform-owned list, because the onboarding screen offers one.

    If owners are later allowed free-text services, add `venue_services.custom_name`
    rather than letting them write into the catalog.
    """

    __tablename__ = "service_catalog"

    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    icon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    applies_to_venue_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("venue_types.id", ondelete="SET NULL"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
