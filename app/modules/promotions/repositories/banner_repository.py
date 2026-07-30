from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Subquery, case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.localization.models import Language
from app.modules.promotions.models import Banner, BannerTranslation


@dataclass(frozen=True, slots=True)
class BannerRow:
    banner: Banner
    title: str
    subtitle: str | None


class BannerRepository:
    """Backs the "Eng yaxshi takliflar" carousel."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _translation_subquery(self, language_id: int) -> Subquery:
        priority = case(
            (BannerTranslation.language_id == language_id, 0),
            (Language.code == "uz", 1),
            (Language.code == "en", 2),
            else_=3,
        )
        return (
            select(
                BannerTranslation.banner_id.label("banner_id"),
                BannerTranslation.title.label("title"),
                BannerTranslation.subtitle.label("subtitle"),
            )
            .join(Language, Language.id == BannerTranslation.language_id)
            .distinct(BannerTranslation.banner_id)
            .order_by(BannerTranslation.banner_id, priority)
            .subquery()
        )

    async def list_active(self, language_id: int, now: datetime) -> Sequence[BannerRow]:
        """Inside the scheduling window and flagged active — both must hold."""
        translations = self._translation_subquery(language_id)
        result = await self.session.execute(
            select(Banner, translations.c.title, translations.c.subtitle)
            .outerjoin(translations, translations.c.banner_id == Banner.id)
            .where(
                Banner.is_active.is_(True),
                Banner.starts_at <= now,
                Banner.ends_at >= now,
            )
            .order_by(Banner.sort_order, Banner.id)
        )
        return [
            BannerRow(banner=row[0], title=row[1] or "", subtitle=row[2]) for row in result.all()
        ]
