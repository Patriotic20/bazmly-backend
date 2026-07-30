from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class MenuCategoryTranslation(IdIntPk, TimestampMixin, Base):
    __tablename__ = "menu_category_translations"
    __table_args__ = (UniqueConstraint("menu_category_id", "language_id"),)

    menu_category_id: Mapped[int] = mapped_column(
        ForeignKey("menu_categories.id", ondelete="CASCADE"), nullable=False
    )
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
