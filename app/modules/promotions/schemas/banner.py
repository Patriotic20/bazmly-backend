from datetime import datetime

from app.core.schemas import ReadSchema
from app.modules.promotions.enums import BannerTargetType


class BannerRead(ReadSchema):
    """Eng yaxshi takliflar karuseli."""

    id: int
    image_url: str
    title: str
    subtitle: str | None = None
    target_type: BannerTargetType
    target_id: int | None = None
    target_url: str | None = None
    sort_order: int
    starts_at: datetime
    ends_at: datetime
