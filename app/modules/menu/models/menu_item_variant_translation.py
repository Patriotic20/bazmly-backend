from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class MenuItemVariantTranslation(IdIntPk, TimestampMixin, Base):
    """Kichik / O'rtacha / Katta are user-visible strings, so they get a table."""

    __tablename__ = "menu_item_variant_translations"
    __table_args__ = (UniqueConstraint("variant_id", "language_id"),)

    variant_id: Mapped[int] = mapped_column(
        ForeignKey("menu_item_variants.id", ondelete="CASCADE"), nullable=False
    )
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
