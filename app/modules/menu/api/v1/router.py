"""Menyu — staff-facing builder.

The customer-facing menu is served from `/v1/venues/{venue_id}/menu`, because a
guest reads one branch's menu with resolved prices while an owner edits the
chain's catalogue. Different payloads, different endpoints.
"""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Body, Path, Query, status

from app.core.dependencies import CurrentUser, LanguageId, require_permission
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
    summary="List categories",
    description="Chips with a live item count — the count is never a stored column.",
)
async def list_categories(
    user: CurrentUser,
    language_id: LanguageId,
    service: MenuServiceDep,
    group_id: Annotated[int, Query(ge=1)],
    venue_id: Annotated[int | None, Query(ge=1)] = None,
) -> Sequence[MenuCategoryRead]:
    return await service.list_categories(group_id, language_id, venue_id)


@router.post(
    "/categories",
    response_model=MenuCategoryRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="venue_menu_create_category",
    summary="Create a category",
    description="Categories belong to the chain, not to one filial.",
    dependencies=[require_permission("menu.edit")],
)
async def create_category(
    payload: MenuCategoryCreate,
    user: CurrentUser,
    language_id: LanguageId,
    service: MenuServiceDep,
    group_id: Annotated[int, Query(ge=1)],
) -> MenuCategoryRead:
    return await service.create_category(group_id, language_id, payload)


@router.get(
    "/items",
    response_model=list[MenuItemListItem],
    operation_id="venue_menu_list_items",
    summary="List dishes for a branch",
    description="Only what this filial serves, at its effective price.",
)
async def list_items(
    user: CurrentUser,
    language_id: LanguageId,
    service: MenuServiceDep,
    venue_id: Annotated[int, Query(ge=1)],
    category_id: Annotated[int | None, Query(ge=1)] = None,
) -> Sequence[MenuItemListItem]:
    return await service.list_items(venue_id, language_id, category_id)


@router.post(
    "/items",
    response_model=MenuItemRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="venue_menu_create_item",
    summary="Create a dish",
    description="Menyu builder steps 1-2. Variants replace the base price, never sit beside it.",
    dependencies=[require_permission("menu.edit")],
)
async def create_item(
    payload: MenuItemCreate,
    user: CurrentUser,
    language_id: LanguageId,
    service: MenuServiceDep,
    venue_id: Annotated[int, Query(ge=1)],
    variants: Annotated[list[MenuItemVariantCreate] | None, Body()] = None,
) -> MenuItemRead:
    return await service.create_item(user.id, venue_id, language_id, payload, variants or [])


@router.get(
    "/items/{item_id}",
    response_model=MenuItemRead,
    operation_id="venue_menu_get_item",
    summary="Get a dish",
    description="Absent from a filial that does not serve it, never priced from the catalogue.",
)
async def get_item(
    user: CurrentUser,
    language_id: LanguageId,
    service: MenuServiceDep,
    item_id: Annotated[int, Path(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
) -> MenuItemRead:
    return await service.get_item(item_id, venue_id, language_id)


@router.put(
    "/items/{item_id}/branches",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    operation_id="venue_menu_set_item_branches",
    summary="Set which branches serve a dish",
    description="Builder step 3. Unticked filials lose their row, so the dish disappears there.",
    dependencies=[require_permission("menu.publish")],
)
async def set_item_branches(
    payload: BranchAvailabilityUpdate,
    user: CurrentUser,
    service: MenuServiceDep,
    item_id: Annotated[int, Path(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
) -> None:
    await service.set_branch_availability(user.id, venue_id, item_id, payload)
