from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class MenuCategory(IdIntPk, TimestampMixin, Base):
    """Owned by the chain, not the branch.

    The chip counts (5 on Steyklar) are a live COUNT(*) over available items, not
    a stored column.
    """

    __tablename__ = "menu_categories"
    __table_args__ = (
        Index("ix_menu_categories_venue_group_id_sort_order", "venue_group_id", "sort_order"),
    )

    venue_group_id: Mapped[int] = mapped_column(
        ForeignKey("venue_groups.id", ondelete="CASCADE"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
