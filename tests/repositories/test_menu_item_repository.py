"""The dish belongs to the chain; availability and price belong to the branch."""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.menu.repositories import MenuItemRepository
from tests.repositories import factories

BASE_PRICE = Decimal("45000.00")
OVERRIDE_PRICE = Decimal("52000.00")


async def test_resolve_price_prefers_the_branch_override(session: AsyncSession) -> None:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    item = await factories.make_menu_item(session, group, base_price=BASE_PRICE)
    await factories.make_menu_branch(session, item, venue, price_override=OVERRIDE_PRICE)

    price = await MenuItemRepository(session).resolve_price(item.id, venue.id)

    assert price == OVERRIDE_PRICE


async def test_resolve_price_falls_back_to_the_base_price(session: AsyncSession) -> None:
    """A branch row with a null override sells at the chain's catalogue price."""
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    item = await factories.make_menu_item(session, group, base_price=BASE_PRICE)
    await factories.make_menu_branch(session, item, venue, price_override=None)

    price = await MenuItemRepository(session).resolve_price(item.id, venue.id)

    assert price == BASE_PRICE


async def test_resolve_price_raises_when_the_branch_has_no_row(
    session: AsyncSession,
) -> None:
    """No branch row means the branch does not sell it.

    Falling back to the catalogue price here would be a pricing bug that only
    surfaces on a receipt, so this raises instead.
    """
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    item = await factories.make_menu_item(session, group, base_price=BASE_PRICE)

    with pytest.raises(NotFoundError):
        await MenuItemRepository(session).resolve_price(item.id, venue.id)


async def test_list_for_venue_omits_items_with_no_branch_row(
    session: AsyncSession,
) -> None:
    """An unticked branch's dishes are absent, not merely flagged unavailable."""
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)

    served = await factories.make_menu_item(session, group, name="Osh", base_price=BASE_PRICE)
    await factories.make_menu_branch(session, served, venue, price_override=OVERRIDE_PRICE)

    unticked = await factories.make_menu_item(session, group, name="Manti", base_price=BASE_PRICE)

    rows = await MenuItemRepository(session).list_for_venue(venue.id, category_id=None)

    ids = [row.item.id for row in rows]
    assert served.id in ids
    assert unticked.id not in ids

    row = next(r for r in rows if r.item.id == served.id)
    assert row.effective_price == OVERRIDE_PRICE
    assert row.name == "Osh"


async def test_set_branch_availability_adds_and_removes_branches(
    session: AsyncSession,
) -> None:
    """Step 3 of the builder: unticking a branch deletes its row outright."""
    group = await factories.make_venue_group(session)
    first_venue = await factories.make_venue(session, group=group, name="Chilonzor")
    second_venue = await factories.make_venue(session, group=group, name="Yunusobod")
    item = await factories.make_menu_item(session, group, base_price=BASE_PRICE)
    repository = MenuItemRepository(session)

    await repository.set_branch_availability(
        item.id,
        [first_venue.id, second_venue.id],
        {second_venue.id: OVERRIDE_PRICE},
    )

    assert await repository.resolve_price(item.id, first_venue.id) == BASE_PRICE
    assert await repository.resolve_price(item.id, second_venue.id) == OVERRIDE_PRICE

    # Untick the first branch.
    await repository.set_branch_availability(item.id, [second_venue.id], {})

    with pytest.raises(NotFoundError):
        await repository.resolve_price(item.id, first_venue.id)

    remaining = await repository.list_for_venue(second_venue.id, category_id=None)
    assert [row.item.id for row in remaining] == [item.id]
    # The override was cleared by the second call, which passed no overrides.
    assert remaining[0].effective_price == BASE_PRICE
