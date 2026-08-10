from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.services.enums import ServicePriceUnit
from app.modules.services.models import VenueService, VenueServiceItem
from app.modules.services.repositories import (
    ServiceCatalogRepository,
    VenueServiceRepository,
)
from app.modules.services.schemas import (
    ServiceCatalogRead,
    VenueServiceCreate,
    VenueServiceItemRead,
    VenueServiceRead,
)
from app.modules.staff.services import StaffService

PERM_SETTINGS_EDIT = "settings.edit"


class VenueServiceCatalogService:
    """Qo'shimcha xizmatlar: a closed platform catalogue, priced per chain or branch.

    This is the single writable source for the dasturxon — the customer-facing
    package view is derived from it, which is why there are no `catering_packages`.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.catalog = ServiceCatalogRepository(session)
        self.venue_services = VenueServiceRepository(session)
        self.staff = StaffService(session)

    async def list_catalog(self, venue_type_id: int | None = None) -> Sequence[ServiceCatalogRead]:
        rows = await self.catalog.list_active(venue_type_id)
        return [
            ServiceCatalogRead(
                id=row.id,
                slug=row.slug,
                name=row.name,
                icon_url=row.icon_url,
                applies_to_venue_type_id=row.applies_to_venue_type_id,
                sort_order=row.sort_order,
            )
            for row in rows
        ]

    async def list_for_venue(self, venue_id: int, group_id: int) -> Sequence[VenueServiceRead]:
        """Branch prices win over chain prices for the same catalogue entry."""
        rows = await self.venue_services.list_for_venue(venue_id, group_id)
        result: list[VenueServiceRead] = []
        for row in rows:
            items = await self.venue_services.list_items(row.service.id)
            result.append(
                VenueServiceRead(
                    id=row.service.id,
                    venue_group_id=row.service.venue_group_id,
                    venue_id=row.service.venue_id,
                    service_catalog_id=row.service.service_catalog_id,
                    name=row.name,
                    price=row.service.price,
                    currency=row.service.currency,
                    price_unit=ServicePriceUnit(row.service.price_unit),
                    is_active=row.service.is_active,
                    sort_order=row.service.sort_order,
                    items=[VenueServiceItemRead.model_validate(item) for item in items],
                )
            )
        return result

    async def create(
        self, actor_user_id: int, venue_id: int, group_id: int, payload: VenueServiceCreate
    ) -> VenueServiceRead:
        """A service and its nested Taomlar rows, in one transaction."""
        await self.staff.require_permission_in_transaction(
            actor_user_id, venue_id, PERM_SETTINGS_EDIT
        )
        catalog_entry = await self.catalog.get_by_id(payload.service_catalog_id)
        if catalog_entry is None:
            raise NotFoundError("Bu xizmat katalogda yo'q")

        service = await self.venue_services.create(
            VenueService(
                venue_group_id=group_id,
                venue_id=payload.venue_id,
                service_catalog_id=payload.service_catalog_id,
                price=payload.price,
                currency=payload.currency,
                price_unit=payload.price_unit,
                is_active=True,
                sort_order=payload.sort_order,
            )
        )
        items = []
        for entry in payload.items:
            items.append(
                await self.venue_services.add_item(
                    VenueServiceItem(
                        venue_service_id=service.id,
                        name=entry.name,
                        price=entry.price,
                        sort_order=entry.sort_order,
                    )
                )
            )
        await self.session.commit()

        return VenueServiceRead(
            id=service.id,
            venue_group_id=service.venue_group_id,
            venue_id=service.venue_id,
            service_catalog_id=service.service_catalog_id,
            name=catalog_entry.slug,
            price=service.price,
            currency=service.currency,
            price_unit=ServicePriceUnit(service.price_unit),
            is_active=service.is_active,
            sort_order=service.sort_order,
            items=[VenueServiceItemRead.model_validate(item) for item in items],
        )
