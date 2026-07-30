from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class MenuItemBranch(IdIntPk, TimestampMixin, Base):
    """Per-branch availability and price for a dish.

    A row exists only for branches the owner ticked; an unticked branch has no row
    and does not show the dish. Price resolution: `price_override` →
    `menu_items.base_price` → error.

    Per-variant overrides are rows in `menu_item_variant_branches`, not JSONB here.
    """

    __tablename__ = "menu_item_branches"
    __table_args__ = (UniqueConstraint("menu_item_id", "venue_id"),)

    menu_item_id: Mapped[int] = mapped_column(
        ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False
    )
    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
    )
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    price_override: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
