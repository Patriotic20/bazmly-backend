from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class MenuItemStatus(StrEnum):
    ACTIVE = "active"
    HIDDEN = "hidden"
    OUT_OF_STOCK = "out_of_stock"


class MenuItem(IdIntPk, TimestampMixin, Base):
    """A dish. Belongs to the chain; availability and price belong to the branch.

    Variants replace the base price, they do not sit beside it — enforced by a
    CHECK, not a convention, so no price read has to guess which column is
    authoritative.
    """

    __tablename__ = "menu_items"
    __table_args__ = (
        Index(
            "ix_menu_items_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        CheckConstraint(
            "(has_variants = false AND base_price IS NOT NULL)"
            " OR (has_variants = true AND base_price IS NULL)",
            name="ck_menu_items_variants_xor_base_price",
        ),
        CheckConstraint(
            "status IN ('active', 'hidden', 'out_of_stock')", name="ck_menu_items_status"
        ),
    )

    menu_category_id: Mapped[int] = mapped_column(
        ForeignKey("menu_categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    base_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="UZS", nullable=False)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    has_variants: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=MenuItemStatus.ACTIVE, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
