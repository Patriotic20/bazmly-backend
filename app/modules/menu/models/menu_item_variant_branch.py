from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class MenuItemVariantBranch(IdIntPk, TimestampMixin, Base):
    """Per-branch price override for one variant.

    Replaces the `variant_price_overrides` JSONB map: rows are joinable,
    constrainable and migratable, and a `{variant_id: price}` blob is none of those
    once a variant is deleted.
    """

    __tablename__ = "menu_item_variant_branches"
    __table_args__ = (UniqueConstraint("variant_id", "venue_id"),)

    variant_id: Mapped[int] = mapped_column(
        ForeignKey("menu_item_variants.id", ondelete="CASCADE"), nullable=False
    )
    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    price_override: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
