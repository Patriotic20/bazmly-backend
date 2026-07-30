from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class ServiceCatalogTranslation(IdIntPk, TimestampMixin, Base):
    __tablename__ = "service_catalog_translations"
    __table_args__ = (UniqueConstraint("service_catalog_id", "language_id"),)

    service_catalog_id: Mapped[int] = mapped_column(
        ForeignKey("service_catalog.id", ondelete="CASCADE"), nullable=False
    )
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
