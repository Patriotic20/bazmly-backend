from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.localization.repositories import LanguageRepository
from app.modules.menu.enums import MenuItemStatus
from app.modules.menu.models import (
    MenuCategory,
    MenuItem,
    MenuItemVariant,
)
from app.modules.menu.repositories import MenuCategoryRepository, MenuItemRepository
from app.modules.menu.schemas import (
    BranchAvailabilityUpdate,
    MenuCategoryCreate,
    MenuCategoryRead,
    MenuItemCreate,
    MenuItemListItem,
    MenuItemRead,
    MenuItemVariantCreate,
    MenuItemVariantRead,
)
from app.modules.staff.services import StaffService

PERM_MENU_EDIT = "menu.edit"


class MenuService:
    """The dish belongs to the chain; availability and price belong to the branch.

    A dish with no `menu_item_branches` row for a venue is **not orderable there**.
    Asking for its price raises rather than falling back to the catalogue price —
    a silent fallback would be a pricing bug that only surfaces on a receipt.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.categories = MenuCategoryRepository(session)
        self.items = MenuItemRepository(session)
        self.languages = LanguageRepository(session)
        self.staff = StaffService(session)

    async def list_categories(
        self, group_id: int, venue_id: int | None = None
    ) -> Sequence[MenuCategoryRead]:
        rows = await self.categories.list_for_group(group_id, venue_id)
        return [
            MenuCategoryRead(
                id=row.category.id,
                name=row.name,
                sort_order=row.category.sort_order,
                is_active=row.category.is_active,
                item_count=row.item_count,
            )
            for row in rows
        ]

    async def list_items(
        self, venue_id: int, category_id: int | None = None
    ) -> Sequence[MenuItemListItem]:
        """Only what this branch actually serves."""
        rows = await self.items.list_for_venue(venue_id, category_id)
        return [
            MenuItemListItem(
                id=row.item.id,
                name=row.name,
                photo_url=row.item.photo_url,
                effective_price=row.effective_price,
                currency=row.item.currency,
                discount_percent=row.item.discount_percent,
                has_variants=row.item.has_variants,
                is_available=row.is_available,
                status=MenuItemStatus(row.item.status),
            )
            for row in rows
        ]

    async def get_item(self, item_id: int, venue_id: int) -> MenuItemRead:
        detail = await self.items.get_with_variants(item_id, venue_id)
        if detail is None:
            raise NotFoundError("Bu taom ushbu filial menyusida yo'q")
        return MenuItemRead(
            id=detail.item.id,
            menu_category_id=detail.item.menu_category_id,
            name=detail.name,
            description=detail.description,
            base_price=detail.item.base_price,
            effective_price=detail.effective_price,
            currency=detail.item.currency,
            photo_url=detail.item.photo_url,
            has_variants=detail.item.has_variants,
            discount_percent=detail.item.discount_percent,
            sort_order=detail.item.sort_order,
            is_available=detail.item.is_available,
            status=MenuItemStatus(detail.item.status),
            variants=[
                MenuItemVariantRead(
                    id=variant.variant.id,
                    name=variant.name,
                    price=variant.variant.price,
                    effective_price=variant.effective_price,
                    sort_order=variant.variant.sort_order,
                    is_active=variant.variant.is_active,
                )
                for variant in detail.variants
            ],
        )

    async def resolve_price_in_transaction(
        self, item_id: int, venue_id: int, variant_id: int | None = None
    ) -> Decimal:
        """Override → base/variant → raise. There is no fourth branch."""
        return await self.items.resolve_price(item_id, venue_id, variant_id)

    async def create_category(self, group_id: int, payload: MenuCategoryCreate) -> MenuCategoryRead:
        category = await self.categories.create(
            MenuCategory(
                venue_group_id=group_id,
                name=payload.name,
                sort_order=payload.sort_order,
                is_active=True,
            )
        )
        await self.session.commit()
        return MenuCategoryRead(
            id=category.id,
            name=payload.name,
            sort_order=category.sort_order,
            is_active=category.is_active,
            item_count=0,
        )

    async def create_item(
        self,
        actor_user_id: int,
        venue_id: int,
        payload: MenuItemCreate,
        variants: Sequence[MenuItemVariantCreate] = (),
    ) -> MenuItemRead:
        """Catalogue write, gated on `menu.edit` at the acting branch."""
        await self.staff.require_permission_in_transaction(actor_user_id, venue_id, PERM_MENU_EDIT)

        item = await self.items.create(
            MenuItem(
                menu_category_id=payload.menu_category_id,
                name=payload.name,
                description=payload.description,
                base_price=payload.base_price,
                currency=payload.currency,
                photo_url=payload.photo_url,
                is_available=True,
                sort_order=payload.sort_order,
                has_variants=payload.has_variants,
                discount_percent=payload.discount_percent,
                status=MenuItemStatus.ACTIVE,
            )
        )

        for variant in variants:
            await self.items.add_variant(
                MenuItemVariant(
                    menu_item_id=item.id,
                    name=variant.name,
                    price=variant.price,
                    sort_order=variant.sort_order,
                    is_active=True,
                )
            )

        await self.session.commit()
        return await self.get_item(item.id, venue_id)

    async def set_branch_availability(
        self,
        actor_user_id: int,
        venue_id: int,
        item_id: int,
        payload: BranchAvailabilityUpdate,
    ) -> None:
        """Builder step 3: upsert ticked branches, delete unticked ones, one
        transaction.

        Deleting rather than flagging is what makes the dish disappear from an
        unticked branch's menu entirely.
        """
        await self.staff.require_permission_in_transaction(actor_user_id, venue_id, PERM_MENU_EDIT)
        item = await self.items.get_by_id(item_id)
        if item is None:
            raise NotFoundError("Taom topilmadi")

        await self.items.set_branch_availability(
            item_id,
            payload.venue_ids,
            {vid: price for vid, price in payload.price_overrides.items()},
        )
        await self.session.commit()
