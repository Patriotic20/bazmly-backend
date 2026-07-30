from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Subquery, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.localization.models import Language
from app.modules.services.models import ServiceCatalog, ServiceCatalogTranslation


@dataclass(frozen=True, slots=True)
class ServiceCatalogRow:
    service: ServiceCatalog
    name: str


class ServiceCatalogRepository:
    """A closed, platform-owned list — owners pick from it, they cannot write to it."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _translation_subquery(self, language_id: int) -> Subquery:
        priority = case(
            (ServiceCatalogTranslation.language_id == language_id, 0),
            (Language.code == "uz", 1),
            (Language.code == "en", 2),
            else_=3,
        )
        return (
            select(
                ServiceCatalogTranslation.service_catalog_id.label("service_catalog_id"),
                ServiceCatalogTranslation.name.label("name"),
            )
            .join(Language, Language.id == ServiceCatalogTranslation.language_id)
            .distinct(ServiceCatalogTranslation.service_catalog_id)
            .order_by(ServiceCatalogTranslation.service_catalog_id, priority)
            .subquery()
        )

    async def get_by_id(self, service_id: int) -> ServiceCatalog | None:
        result = await self.session.execute(
            select(ServiceCatalog).where(ServiceCatalog.id == service_id)
        )
        return result.scalar_one_or_none()

    async def list_active(
        self, language_id: int, venue_type_id: int | None = None
    ) -> Sequence[ServiceCatalogRow]:
        """A null `applies_to_venue_type_id` means the service suits any venue, so
        it is always included alongside the type-specific ones."""
        translations = self._translation_subquery(language_id)
        stmt = (
            select(ServiceCatalog, translations.c.name)
            .outerjoin(translations, translations.c.service_catalog_id == ServiceCatalog.id)
            .where(ServiceCatalog.is_active.is_(True))
        )
        if venue_type_id is not None:
            stmt = stmt.where(
                or_(
                    ServiceCatalog.applies_to_venue_type_id.is_(None),
                    ServiceCatalog.applies_to_venue_type_id == venue_type_id,
                )
            )
        result = await self.session.execute(stmt.order_by(ServiceCatalog.sort_order))
        return [
            ServiceCatalogRow(service=row[0], name=row[1] or row[0].slug) for row in result.all()
        ]
