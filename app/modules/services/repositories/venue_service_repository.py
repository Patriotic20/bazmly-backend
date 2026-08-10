from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.services.models import (
    ServiceCatalog,
    VenueService,
    VenueServiceItem,
)


@dataclass(frozen=True, slots=True)
class VenueServiceRow:
    service: VenueService
    catalog: ServiceCatalog
    name: str


@dataclass(frozen=True, slots=True)
class VenueServiceWithItems:
    service: VenueService
    items: Sequence[VenueServiceItem]


class VenueServiceRepository:
    """The single writable source for the dasturxon. `venue_id IS NULL` is a
    chain-wide price; a branch row overrides it."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, service_id: int) -> VenueService | None:
        result = await self.session.execute(
            select(VenueService).where(VenueService.id == service_id)
        )
        return result.scalar_one_or_none()

    async def list_for_venue(self, venue_id: int, group_id: int) -> Sequence[VenueServiceRow]:
        """Branch rows win over chain rows for the same catalog entry.

        `DISTINCT ON (service_catalog_id)` ordered by "branch row first" collapses
        the two candidates to one without a second query or a Python-side merge.
        """
        specificity = case((VenueService.venue_id.is_not(None), 0), else_=1)

        preferred = (
            select(VenueService.id.label("service_id"))
            .where(
                VenueService.venue_group_id == group_id,
                VenueService.is_active.is_(True),
                or_(VenueService.venue_id == venue_id, VenueService.venue_id.is_(None)),
            )
            .distinct(VenueService.service_catalog_id)
            .order_by(VenueService.service_catalog_id, specificity)
            .subquery()
        )

        result = await self.session.execute(
            select(VenueService, ServiceCatalog, ServiceCatalog.name)
            .join(preferred, preferred.c.service_id == VenueService.id)
            .join(ServiceCatalog, ServiceCatalog.id == VenueService.service_catalog_id)
            .order_by(VenueService.sort_order, VenueService.id)
        )
        return [
            VenueServiceRow(service=row[0], catalog=row[1], name=row[2] or row[1].slug)
            for row in result.all()
        ]

    async def get_with_items(self, service_id: int) -> VenueServiceWithItems | None:
        """The Taomlar rows nested under Dasturxon tuzash."""
        service = await self.get_by_id(service_id)
        if service is None:
            return None
        result = await self.session.execute(
            select(VenueServiceItem)
            .where(VenueServiceItem.venue_service_id == service_id)
            .order_by(VenueServiceItem.sort_order, VenueServiceItem.id)
        )
        return VenueServiceWithItems(service=service, items=result.scalars().all())

    async def create(self, service: VenueService) -> VenueService:
        self.session.add(service)
        await self.session.flush()
        return service

    async def add_item(self, item: VenueServiceItem) -> VenueServiceItem:
        self.session.add(item)
        await self.session.flush()
        return item

    async def list_items(self, venue_service_id: int) -> Sequence[VenueServiceItem]:
        result = await self.session.execute(
            select(VenueServiceItem)
            .where(VenueServiceItem.venue_service_id == venue_service_id)
            .order_by(VenueServiceItem.sort_order, VenueServiceItem.id)
        )
        return result.scalars().all()
