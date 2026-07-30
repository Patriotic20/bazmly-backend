from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class BannerTargetType(StrEnum):
    VENUE = "venue"
    CATEGORY = "category"
    PROMO = "promo"
    URL = "url"


class Banner(IdIntPk, TimestampMixin, Base):
    """Backs the "Eng yaxshi takliflar" carousel."""

    __tablename__ = "banners"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('venue', 'category', 'promo', 'url')",
            name="ck_banners_target_type",
        ),
    )

    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
