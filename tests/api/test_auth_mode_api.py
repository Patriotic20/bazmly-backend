"""What `AUTH_MODE=disabled` actually opens.

The point of these tests is the second layer. Permission checks run in twelve
service methods as well as in the route guard, so a switch that only silenced the
guard would open the reads and leave every staff write at 403 — working badly
enough to look broken, and just well enough to be believed.
"""

from collections.abc import Iterator
from datetime import time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AuthMode, settings
from tests.repositories import factories


@pytest.fixture
def auth_off() -> Iterator[None]:
    saved = (settings.security.auth_mode, settings.security.dev_user_id)
    settings.security.auth_mode = AuthMode.DISABLED
    yield
    settings.security.auth_mode, settings.security.dev_user_id = saved


async def test_a_staff_write_needs_no_token(
    api_client: AsyncClient, session: AsyncSession, auth_off: None
) -> None:
    """The whole switch in one assertion. Unauthenticated, unemployed, and 200.

    This request is a 401 with the switch off (`test_permissions_api`) and a 403
    for anyone without `branch.manage` (`test_waiter_cannot_edit_a_branch`).
    """
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    outsider = await factories.make_user(session)
    settings.security.dev_user_id = outsider.id

    response = await api_client.patch(
        f"/api/v1/venue/venues/{venue.id}", json={"street": "Yangi ko'cha"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["street"] == "Yangi ko'cha"


async def test_the_service_layer_is_open_too(
    api_client: AsyncClient, session: AsyncSession, auth_off: None
) -> None:
    """`OrderService.open_table` re-checks `orders.open` itself, past the guard.

    The caller here is a `security` guard — a role that genuinely lacks the
    permission — so a 200 can only mean the service-layer check was skipped, not
    that it happened to pass.
    """
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    await factories.make_working_hours(session, venue, time(8, 0), time(23, 0))
    table = await factories.make_table(session, venue, number=1, seats=4)
    doorman = await factories.make_staff(session, venue, group, role_slug="security")
    settings.security.dev_user_id = doorman.user_id

    response = await api_client.post(
        "/api/v1/venue/orders",
        params={"venue_id": venue.id},
        json={"table_id": table.id, "guests_count": 2},
    )

    assert response.status_code == 201, response.text


async def test_every_request_is_the_dev_user(
    api_client: AsyncClient, session: AsyncSession, auth_off: None
) -> None:
    user = await factories.make_user(session)
    settings.security.dev_user_id = user.id

    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json()["id"] == user.id


async def test_a_missing_dev_user_is_reported_as_a_misconfiguration(
    api_client: AsyncClient, auth_off: None
) -> None:
    """Not a 404. `get_profile` would call it "user not found", which sends the
    reader looking for a bug in the request instead of in the .env."""
    settings.security.dev_user_id = 10_000_000

    with pytest.raises(Exception, match="DEV_USER_ID"):
        await api_client.get("/api/v1/users/me")


async def test_the_switch_off_still_refuses(api_client: AsyncClient) -> None:
    """No fixture here on purpose — this is the shipped default."""
    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 401
