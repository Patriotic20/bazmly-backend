"""A dish with no branch row is not orderable there — never a silent fallback."""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.menu.services import MenuService
from tests.repositories import factories

BASE_PRICE = Decimal("45000.00")
OVERRIDE = Decimal("52000.00")


async def test_item_with_no_branch_row_raises(session: AsyncSession) -> None:
    """The whole rule in one assertion.

    Falling back to the chain's catalogue price would be a pricing bug that only
    surfaces on a printed receipt, so this raises instead.
    """
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    item = await factories.make_menu_item(session, group, base_price=BASE_PRICE)

    with pytest.raises(NotFoundError):
        await MenuService(session).resolve_price_in_transaction(item.id, venue.id)


async def test_get_item_for_a_branch_that_does_not_serve_it_raises(
    session: AsyncSession,
) -> None:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    item = await factories.make_menu_item(session, group, base_price=BASE_PRICE)

    with pytest.raises(NotFoundError):
        await MenuService(session).get_item(item.id, venue.id)


async def test_branch_override_wins_over_the_base_price(session: AsyncSession) -> None:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    item = await factories.make_menu_item(session, group, base_price=BASE_PRICE)
    await factories.make_menu_branch(session, item, venue, price_override=OVERRIDE)

    price = await MenuService(session).resolve_price_in_transaction(item.id, venue.id)

    assert price == OVERRIDE


async def test_base_price_is_used_when_the_branch_sets_no_override(
    session: AsyncSession,
) -> None:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    item = await factories.make_menu_item(session, group, base_price=BASE_PRICE)
    await factories.make_menu_branch(session, item, venue, price_override=None)

    price = await MenuService(session).resolve_price_in_transaction(item.id, venue.id)

    assert price == BASE_PRICE


async def test_list_items_omits_dishes_the_branch_does_not_serve(
    session: AsyncSession,
) -> None:
    """Absent, not merely flagged unavailable."""
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)

    served = await factories.make_menu_item(session, group, name="Osh", base_price=BASE_PRICE)
    await factories.make_menu_branch(session, served, venue, price_override=OVERRIDE)
    unticked = await factories.make_menu_item(session, group, name="Manti", base_price=BASE_PRICE)

    rows = await MenuService(session).list_items(venue.id)

    ids = [row.id for row in rows]
    assert served.id in ids
    assert unticked.id not in ids
    assert next(row for row in rows if row.id == served.id).effective_price == OVERRIDE
