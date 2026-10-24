from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError
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
    VenueServiceUpdate,
)
from app.modules.staff.services import StaffService
from app.modules.venues.enums import VenueTypeSlug
from app.modules.venues.repositories import VenueRepository

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
        self.venues = VenueRepository(session)

    async def _chain_of(self, venue_id: int) -> int:
        venue = await self.venues.get_by_id(venue_id)
        if venue is None:
            raise NotFoundError("Muassasa topilmadi")
        return venue.venue_group_id

    async def _editable_in_transaction(
        self, actor_user_id: int, venue_id: int, service_id: int
    ) -> VenueService:
        """The service, once the actor may edit it from this branch.

        The guard proves `settings.edit` at the branch in the query; the row must
        also belong to that branch's chain — and be its own or chain-wide — or
        any id would reach another chain's prices.
        """
        await self.staff.require_permission_in_transaction(
            actor_user_id, venue_id, PERM_SETTINGS_EDIT
        )
        service = await self.venue_services.get_by_id(service_id)
        if (
            service is None
            or service.venue_group_id != await self._chain_of(venue_id)
            or service.venue_id not in (None, venue_id)
        ):
            raise NotFoundError("Xizmat topilmadi")
        return service

    async def _read(self, service: VenueService) -> VenueServiceRead:
        items = await self.venue_services.list_items(service.id)
        catalog_entry = await self.catalog.get_by_id(service.service_catalog_id)
        return VenueServiceRead(
            id=service.id,
            venue_group_id=service.venue_group_id,
            venue_id=service.venue_id,
            service_catalog_id=service.service_catalog_id,
            slug=catalog_entry.slug if catalog_entry else "",
            name=await self.venue_services.catalog_name(service),
            price=service.price,
            currency=service.currency,
            price_unit=ServicePriceUnit(service.price_unit),
            is_active=service.is_active,
            sort_order=service.sort_order,
            items=[VenueServiceItemRead.model_validate(item) for item in items],
        )

    async def list_catalog(
        self, venue_type: VenueTypeSlug | None = None
    ) -> Sequence[ServiceCatalogRead]:
        rows = await self.catalog.list_active(venue_type)
        return [
            ServiceCatalogRead(
                id=row.id,
                slug=row.slug,
                name=row.name,
                icon_url=row.icon_url,
                applies_to_venue_type=(
                    VenueTypeSlug(row.applies_to_venue_type)
                    if row.applies_to_venue_type is not None
                    else None
                ),
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
                    slug=row.catalog.slug,
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
        # `group_id` arrives in the query beside `venue_id`; only the branch is
        # proven by the guard, so the chain has to be that branch's own.
        if group_id != await self._chain_of(venue_id):
            raise PermissionDeniedError("Bu filial ushbu tarmoqqa tegishli emas")
        if payload.venue_id not in (None, venue_id):
            raise PermissionDeniedError("Narxni faqat shu filial uchun belgilash mumkin")
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
            slug=catalog_entry.slug,
            name=catalog_entry.name or catalog_entry.slug,
            price=service.price,
            currency=service.currency,
            price_unit=ServicePriceUnit(service.price_unit),
            is_active=service.is_active,
            sort_order=service.sort_order,
            items=[VenueServiceItemRead.model_validate(item) for item in items],
        )

    async def update(
        self, actor_user_id: int, venue_id: int, service_id: int, payload: VenueServiceUpdate
    ) -> VenueServiceRead:
        service = await self._editable_in_transaction(actor_user_id, venue_id, service_id)
        values = payload.model_dump(exclude_unset=True, exclude={"items"})
        updated = await self.venue_services.update_fields(service.id, values)
        if updated is None:
            raise NotFoundError("Xizmat topilmadi")
        if payload.items is not None:
            await self.venue_services.replace_items(
                service.id,
                [
                    VenueServiceItem(
                        venue_service_id=service.id,
                        name=entry.name,
                        price=entry.price,
                        sort_order=entry.sort_order,
                    )
                    for entry in payload.items
                ],
            )
        await self.session.commit()
        return await self._read(updated)

    async def remove(self, actor_user_id: int, venue_id: int, service_id: int) -> None:
        """Switched off rather than deleted: past bookings still point at it."""
        service = await self._editable_in_transaction(actor_user_id, venue_id, service_id)
        await self.venue_services.update_fields(service.id, {"is_active": False})
        await self.session.commit()
