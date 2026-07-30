from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Subquery, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.localization.models import Language
from app.modules.menu.models import (
    MenuCategory,
    MenuCategoryTranslation,
    MenuItem,
    MenuItemBranch,
    MenuItemStatus,
)


@dataclass(frozen=True, slots=True)
class MenuCategoryRow:
    category: MenuCategory
    name: str
    item_count: int


class MenuCategoryRepository:
    """Categories belong to the chain, not the branch."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _translation_subquery(self, language_id: int) -> Subquery:
        priority = case(
            (MenuCategoryTranslation.language_id == language_id, 0),
            (Language.code == "uz", 1),
            (Language.code == "en", 2),
            else_=3,
        )
        return (
            select(
                MenuCategoryTranslation.menu_category_id.label("menu_category_id"),
                MenuCategoryTranslation.name.label("name"),
            )
            .join(Language, Language.id == MenuCategoryTranslation.language_id)
            .distinct(MenuCategoryTranslation.menu_category_id)
            .order_by(MenuCategoryTranslation.menu_category_id, priority)
            .subquery()
        )

    async def get_by_id(self, category_id: int) -> MenuCategory | None:
        result = await self.session.execute(
            select(MenuCategory).where(MenuCategory.id == category_id)
        )
        return result.scalar_one_or_none()

    async def list_for_group(
        self, group_id: int, language_id: int, venue_id: int | None = None
    ) -> Sequence[MenuCategoryRow]:
        """The chip row. The count on each chip ("5" on Steyklar) is a live
        `COUNT(*)` as a correlated subquery, never a stored column.

        Passing `venue_id` narrows the count to what that branch actually serves,
        which is what the waiter's menu grid needs; omitting it counts the chain's
        catalogue.
        """
        translations = self._translation_subquery(language_id)

        count_stmt = (
            select(func.count())
            .select_from(MenuItem)
            .where(
                MenuItem.menu_category_id == MenuCategory.id,
                MenuItem.is_available.is_(True),
                MenuItem.status == MenuItemStatus.ACTIVE,
            )
        )
        if venue_id is not None:
            count_stmt = count_stmt.where(
                select(MenuItemBranch.id)
                .where(
                    MenuItemBranch.menu_item_id == MenuItem.id,
                    MenuItemBranch.venue_id == venue_id,
                    MenuItemBranch.is_available.is_(True),
                )
                .exists()
            )
        item_count = count_stmt.correlate(MenuCategory).scalar_subquery()

        result = await self.session.execute(
            select(MenuCategory, translations.c.name, item_count)
            .outerjoin(translations, translations.c.menu_category_id == MenuCategory.id)
            .where(
                MenuCategory.venue_group_id == group_id,
                MenuCategory.is_active.is_(True),
            )
            .order_by(MenuCategory.sort_order)
        )
        return [
            MenuCategoryRow(category=row[0], name=row[1] or "", item_count=int(row[2]))
            for row in result.all()
        ]

    async def create(self, category: MenuCategory) -> MenuCategory:
        self.session.add(category)
        await self.session.flush()
        return category

    async def add_translation(
        self, translation: MenuCategoryTranslation
    ) -> MenuCategoryTranslation:
        self.session.add(translation)
        await self.session.flush()
        return translation
