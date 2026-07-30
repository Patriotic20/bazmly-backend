from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import Subquery, case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.localization.models import Language
from app.modules.menu.models import (
    MenuItem,
    MenuItemBranch,
    MenuItemStatus,
    MenuItemTranslation,
    MenuItemVariant,
    MenuItemVariantBranch,
    MenuItemVariantTranslation,
)


@dataclass(frozen=True, slots=True)
class MenuItemRow:
    """A dish as one branch serves it: catalogue row plus the resolved price."""

    item: MenuItem
    name: str
    description: str | None
    effective_price: Decimal | None
    is_available: bool


@dataclass(frozen=True, slots=True)
class MenuItemVariantRow:
    variant: MenuItemVariant
    name: str
    effective_price: Decimal


@dataclass(frozen=True, slots=True)
class MenuItemWithVariants:
    item: MenuItem
    name: str
    description: str | None
    effective_price: Decimal | None
    variants: Sequence[MenuItemVariantRow]


class MenuItemRepository:
    """The dish belongs to the chain; availability and price belong to the branch.

    Price resolution is always `branch override → catalogue price`. A dish with no
    `menu_item_branches` row for a branch is not on that branch's menu at all — it
    is absent, not merely unavailable.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _translation_subquery(self, language_id: int) -> Subquery:
        priority = case(
            (MenuItemTranslation.language_id == language_id, 0),
            (Language.code == "uz", 1),
            (Language.code == "en", 2),
            else_=3,
        )
        return (
            select(
                MenuItemTranslation.menu_item_id.label("menu_item_id"),
                MenuItemTranslation.name.label("name"),
                MenuItemTranslation.description.label("description"),
            )
            .join(Language, Language.id == MenuItemTranslation.language_id)
            .distinct(MenuItemTranslation.menu_item_id)
            .order_by(MenuItemTranslation.menu_item_id, priority)
            .subquery()
        )

    def _variant_translation_subquery(self, language_id: int) -> Subquery:
        priority = case(
            (MenuItemVariantTranslation.language_id == language_id, 0),
            (Language.code == "uz", 1),
            (Language.code == "en", 2),
            else_=3,
        )
        return (
            select(
                MenuItemVariantTranslation.variant_id.label("variant_id"),
                MenuItemVariantTranslation.name.label("name"),
            )
            .join(Language, Language.id == MenuItemVariantTranslation.language_id)
            .distinct(MenuItemVariantTranslation.variant_id)
            .order_by(MenuItemVariantTranslation.variant_id, priority)
            .subquery()
        )

    async def get_by_id(self, item_id: int) -> MenuItem | None:
        result = await self.session.execute(select(MenuItem).where(MenuItem.id == item_id))
        return result.scalar_one_or_none()

    async def list_for_venue(
        self, venue_id: int, category_id: int | None, language_id: int
    ) -> Sequence[MenuItemRow]:
        """Inner-joins `menu_item_branches`, so an unticked branch's dishes simply
        do not appear."""
        translations = self._translation_subquery(language_id)
        effective_price = func.coalesce(MenuItemBranch.price_override, MenuItem.base_price)

        stmt = (
            select(
                MenuItem,
                translations.c.name,
                translations.c.description,
                effective_price,
                MenuItemBranch.is_available,
            )
            .join(MenuItemBranch, MenuItemBranch.menu_item_id == MenuItem.id)
            .outerjoin(translations, translations.c.menu_item_id == MenuItem.id)
            .where(
                MenuItemBranch.venue_id == venue_id,
                MenuItemBranch.is_available.is_(True),
                MenuItem.is_available.is_(True),
                MenuItem.status == MenuItemStatus.ACTIVE,
            )
        )
        if category_id is not None:
            stmt = stmt.where(MenuItem.menu_category_id == category_id)

        result = await self.session.execute(stmt.order_by(MenuItem.sort_order, MenuItem.id))
        return [
            MenuItemRow(
                item=row[0],
                name=row[1] or "",
                description=row[2],
                effective_price=row[3],
                is_available=bool(row[4]),
            )
            for row in result.all()
        ]

    async def get_with_variants(
        self, item_id: int, venue_id: int, language_id: int
    ) -> MenuItemWithVariants | None:
        translations = self._translation_subquery(language_id)
        effective_price = func.coalesce(MenuItemBranch.price_override, MenuItem.base_price)

        head = await self.session.execute(
            select(MenuItem, translations.c.name, translations.c.description, effective_price)
            .join(MenuItemBranch, MenuItemBranch.menu_item_id == MenuItem.id)
            .outerjoin(translations, translations.c.menu_item_id == MenuItem.id)
            .where(MenuItem.id == item_id, MenuItemBranch.venue_id == venue_id)
        )
        row = head.one_or_none()
        if row is None:
            return None

        variant_translations = self._variant_translation_subquery(language_id)
        variant_price = func.coalesce(MenuItemVariantBranch.price_override, MenuItemVariant.price)
        variants = await self.session.execute(
            select(MenuItemVariant, variant_translations.c.name, variant_price)
            .outerjoin(
                MenuItemVariantBranch,
                (MenuItemVariantBranch.variant_id == MenuItemVariant.id)
                & (MenuItemVariantBranch.venue_id == venue_id),
            )
            .outerjoin(
                variant_translations, variant_translations.c.variant_id == MenuItemVariant.id
            )
            .where(
                MenuItemVariant.menu_item_id == item_id,
                MenuItemVariant.is_active.is_(True),
            )
            .order_by(MenuItemVariant.sort_order, MenuItemVariant.id)
        )

        return MenuItemWithVariants(
            item=row[0],
            name=row[1] or "",
            description=row[2],
            effective_price=row[3],
            variants=[
                MenuItemVariantRow(variant=v[0], name=v[1] or "", effective_price=v[2])
                for v in variants.all()
            ],
        )

    async def resolve_price(
        self, item_id: int, venue_id: int, variant_id: int | None = None
    ) -> Decimal:
        """The one price a branch charges right now.

        Raises when the branch has no row for the dish, because there is no
        sensible fallback: an unticked branch does not sell it, and silently
        charging the chain's catalogue price would be a pricing bug that only
        surfaces on the receipt.
        """
        if variant_id is not None:
            result = await self.session.execute(
                select(func.coalesce(MenuItemVariantBranch.price_override, MenuItemVariant.price))
                .select_from(MenuItemVariant)
                .join(
                    MenuItemBranch,
                    (MenuItemBranch.menu_item_id == MenuItemVariant.menu_item_id)
                    & (MenuItemBranch.venue_id == venue_id),
                )
                .outerjoin(
                    MenuItemVariantBranch,
                    (MenuItemVariantBranch.variant_id == MenuItemVariant.id)
                    & (MenuItemVariantBranch.venue_id == venue_id),
                )
                .where(
                    MenuItemVariant.id == variant_id,
                    MenuItemVariant.menu_item_id == item_id,
                )
            )
            price = result.scalar_one_or_none()
            if price is None:
                raise NotFoundError(
                    "No price for this variant at this branch",
                    details={
                        "item_id": item_id,
                        "venue_id": venue_id,
                        "variant_id": variant_id,
                    },
                )
            return price

        result = await self.session.execute(
            select(func.coalesce(MenuItemBranch.price_override, MenuItem.base_price))
            .select_from(MenuItem)
            .join(
                MenuItemBranch,
                (MenuItemBranch.menu_item_id == MenuItem.id)
                & (MenuItemBranch.venue_id == venue_id),
            )
            .where(MenuItem.id == item_id)
        )
        price = result.scalar_one_or_none()
        if price is None:
            raise NotFoundError(
                "No price for this item at this branch",
                details={"item_id": item_id, "venue_id": venue_id},
            )
        return price

    async def set_branch_availability(
        self,
        item_id: int,
        venue_ids: Sequence[int],
        price_overrides: Mapping[int, Decimal | None] | None = None,
    ) -> None:
        """Step 3 of the builder: which branches serve this dish, at what price.

        Unticked branches lose their row entirely rather than being flagged
        unavailable, which is what makes the dish absent from their menu.
        """
        overrides = price_overrides or {}

        delete_stmt = delete(MenuItemBranch).where(MenuItemBranch.menu_item_id == item_id)
        if venue_ids:
            delete_stmt = delete_stmt.where(MenuItemBranch.venue_id.notin_(venue_ids))
        await self.session.execute(delete_stmt)

        for venue_id in venue_ids:
            stmt = pg_insert(MenuItemBranch).values(
                menu_item_id=item_id,
                venue_id=venue_id,
                is_available=True,
                price_override=overrides.get(venue_id),
            )
            await self.session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[
                        MenuItemBranch.menu_item_id,
                        MenuItemBranch.venue_id,
                    ],
                    set_={
                        "is_available": stmt.excluded.is_available,
                        "price_override": stmt.excluded.price_override,
                    },
                )
            )

        await self.session.flush()

    async def create(self, item: MenuItem) -> MenuItem:
        self.session.add(item)
        await self.session.flush()
        return item

    async def update_fields(self, item_id: int, values: dict[str, Any]) -> MenuItem | None:
        if not values:
            return await self.get_by_id(item_id)
        result = await self.session.execute(
            update(MenuItem).where(MenuItem.id == item_id).values(**values).returning(MenuItem)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def add_translation(self, translation: MenuItemTranslation) -> MenuItemTranslation:
        self.session.add(translation)
        await self.session.flush()
        return translation

    async def add_variant(self, variant: MenuItemVariant) -> MenuItemVariant:
        self.session.add(variant)
        await self.session.flush()
        return variant

    async def add_variant_translation(
        self, translation: MenuItemVariantTranslation
    ) -> MenuItemVariantTranslation:
        self.session.add(translation)
        await self.session.flush()
        return translation

    async def list_variants(self, item_id: int) -> Sequence[MenuItemVariant]:
        result = await self.session.execute(
            select(MenuItemVariant)
            .where(MenuItemVariant.menu_item_id == item_id)
            .order_by(MenuItemVariant.sort_order, MenuItemVariant.id)
        )
        return result.scalars().all()
