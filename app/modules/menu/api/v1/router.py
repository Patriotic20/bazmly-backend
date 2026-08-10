"""Menyu — staff-facing builder.

The customer-facing menu is served from `/v1/venues/{venue_id}/menu`, because a
guest reads one branch's menu with resolved prices while an owner edits the
chain's catalogue. Different payloads, different endpoints.
"""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Body, Path, Query, status

from app.core.dependencies import CurrentUser, require_permission
from app.modules.auth.schemas import UserRead
from app.modules.menu.api.dependencies import MenuServiceDep
from app.modules.menu.schemas import (
    BranchAvailabilityUpdate,
    MenuCategoryCreate,
    MenuCategoryRead,
    MenuItemCreate,
    MenuItemListItem,
    MenuItemRead,
    MenuItemVariantCreate,
)

router = APIRouter(prefix="/v1/venue/menu", tags=["venue:menu"])


@router.get(
    "/categories",
    response_model=list[MenuCategoryRead],
    operation_id="venue_menu_list_categories",
    summary="Kategoriyalar ro'yxati",
    description="Har bir kategoriya yonidagi son jonli hisoblanadi, saqlanmaydi.",
)
async def list_categories(
    user: CurrentUser,
    service: MenuServiceDep,
    group_id: Annotated[int, Query(ge=1)],
    venue_id: Annotated[int | None, Query(ge=1)] = None,
) -> Sequence[MenuCategoryRead]:
    return await service.list_categories(group_id, venue_id)


@router.post(
    "/categories",
    response_model=MenuCategoryRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="venue_menu_create_category",
    summary="Kategoriya yaratish",
    description="Kategoriyalar tarmoqqa tegishli, bitta filialga emas.",
    dependencies=[require_permission("menu.edit")],
)
async def create_category(
    payload: MenuCategoryCreate,
    service: MenuServiceDep,
    group_id: Annotated[int, Query(ge=1)],
) -> MenuCategoryRead:
    return await service.create_category(group_id, payload)


@router.get(
    "/items",
    response_model=list[MenuItemListItem],
    operation_id="venue_menu_list_items",
    summary="Filial taomlari",
    description="Faqat shu filial taqdim etadigan taomlar, amaldagi narxi bilan.",
)
async def list_items(
    user: CurrentUser,
    service: MenuServiceDep,
    venue_id: Annotated[int, Query(ge=1)],
    category_id: Annotated[int | None, Query(ge=1)] = None,
) -> Sequence[MenuItemListItem]:
    return await service.list_items(venue_id, category_id)


@router.post(
    "/items",
    response_model=MenuItemRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="venue_menu_create_item",
    summary="Taom yaratish",
    description=(
        "Menyu konstruktori, 1-2 bosqich. Variantlar asosiy narx o'rnini "
        "egallaydi, u bilan birga turmaydi."
    ),
)
async def create_item(
    payload: MenuItemCreate,
    user: Annotated[UserRead, require_permission("menu.edit")],
    service: MenuServiceDep,
    venue_id: Annotated[int, Query(ge=1)],
    variants: Annotated[list[MenuItemVariantCreate] | None, Body()] = None,
) -> MenuItemRead:
    return await service.create_item(user.id, venue_id, payload, variants or [])


@router.get(
    "/items/{item_id}",
    response_model=MenuItemRead,
    operation_id="venue_menu_get_item",
    summary="Taom ma'lumoti",
    description=(
        "Taom taqdim etilmaydigan filialda umuman ko'rinmaydi va katalog narxi bilan sotilmaydi."
    ),
)
async def get_item(
    user: CurrentUser,
    service: MenuServiceDep,
    item_id: Annotated[int, Path(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
) -> MenuItemRead:
    return await service.get_item(item_id, venue_id)


@router.put(
    "/items/{item_id}/branches",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    operation_id="venue_menu_set_item_branches",
    summary="Taomni filiallarga biriktirish",
    description=(
        "Konstruktorning 3-bosqichi. Belgilanmagan filialdan taom butunlay olib tashlanadi."
    ),
)
async def set_item_branches(
    payload: BranchAvailabilityUpdate,
    user: Annotated[UserRead, require_permission("menu.publish")],
    service: MenuServiceDep,
    item_id: Annotated[int, Path(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
) -> None:
    await service.set_branch_availability(user.id, venue_id, item_id, payload)
