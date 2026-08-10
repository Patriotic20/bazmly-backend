from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class VenueGroupStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    BLOCKED = "blocked"


class VenueGroup(IdIntPk, TimestampMixin, Base):
    """The chain. Every venue belongs to one, including a single restaurant.

    A group of one costs one row; a nullable `venue_group_id` would cost two code
    paths in every menu query, permission check and dashboard aggregate forever.
    `logo_url` lives here and nowhere else.
    """

    __tablename__ = "venue_groups"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'active', 'blocked')", name="ck_venue_groups_status"),
        # Spelled out rather than derived from `VenueTypeSlug`: a model may not
        # import another module's model file, and the enum lives beside `Venue`.
        CheckConstraint(
            "primary_venue_type IN ('restoran', 'toyxona')",
            name="ck_venue_groups_primary_venue_type",
        ),
    )

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    primary_venue_type: Mapped[str] = mapped_column(String(20), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_currency: Mapped[str] = mapped_column(String(3), default="UZS", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=VenueGroupStatus.DRAFT, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
