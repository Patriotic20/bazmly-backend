from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.services.models import ServiceCatalog


class ServiceCatalogRepository:
    """A closed, platform-owned list — owners pick from it, they cannot write to it."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, service_id: int) -> ServiceCatalog | None:
        result = await self.session.execute(
            select(ServiceCatalog).where(ServiceCatalog.id == service_id)
        )
        return result.scalar_one_or_none()

    async def list_active(self, venue_type_id: int | None = None) -> Sequence[ServiceCatalog]:
        """A null `applies_to_venue_type_id` means the service suits any venue, so
        it is always included alongside the type-specific ones."""
        stmt = select(ServiceCatalog).where(ServiceCatalog.is_active.is_(True))
        if venue_type_id is not None:
            stmt = stmt.where(
                or_(
                    ServiceCatalog.applies_to_venue_type_id.is_(None),
                    ServiceCatalog.applies_to_venue_type_id == venue_type_id,
                )
            )
        result = await self.session.execute(stmt.order_by(ServiceCatalog.sort_order))
        return list(result.scalars().all())
