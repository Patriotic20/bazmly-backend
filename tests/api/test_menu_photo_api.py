"""A dish photo: uploaded once, served back, and written onto the dish by an edit."""

from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import auth_header
from tests.repositories import factories

MENU_EDIT = "menu.edit"

# The smallest valid PNG header; the service sniffs the signature, not the pixels.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


async def test_uploaded_image_is_served_back_from_its_url(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    user = await factories.make_user(session)

    response = await api_client.post(
        "/api/v1/media/images",
        files={"file": ("osh.png", PNG, "image/png")},
        headers=auth_header(user.id),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["content_type"] == "image/png"
    assert body["url"].startswith("http://test/api/v1/media/images/")

    served = await api_client.get(body["url"].removeprefix("http://test"))
    assert served.status_code == 200
    assert served.content == PNG
    assert served.headers["content-type"] == "image/png"


async def test_a_file_that_is_not_an_image_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The client's Content-Type is ignored — these bytes are served to everyone."""
    user = await factories.make_user(session)

    response = await api_client.post(
        "/api/v1/media/images",
        files={"file": ("osh.png", b"<script>alert(1)</script>", "image/png")},
        headers=auth_header(user.id),
    )

    assert response.status_code == 422


async def test_upload_needs_a_signed_in_caller(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/media/images", files={"file": ("osh.png", PNG, "image/png")}
    )

    assert response.status_code == 401


async def test_manager_edits_a_dish_and_its_photo(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    item = await factories.make_menu_item(session, group)
    await factories.make_menu_branch(session, item, venue)
    manager = await factories.make_staff(session, venue, group, role_slug="manager")
    await factories.grant(session, "manager", MENU_EDIT)

    response = await api_client.patch(
        f"/api/v1/venue/menu/items/{item.id}",
        params={"venue_id": venue.id},
        json={
            "name": "To'y oshi",
            "base_price": "60000",
            "photo_url": "https://example.test/osh.jpg",
        },
        headers=auth_header(manager.user_id),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "To'y oshi"
    assert Decimal(body["base_price"]) == Decimal("60000")
    assert body["photo_url"] == "https://example.test/osh.jpg"


async def test_a_dish_another_branch_offers_is_not_editable_from_here(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    elsewhere = await factories.make_venue(session, group=group)
    item = await factories.make_menu_item(session, group)
    await factories.make_menu_branch(session, item, elsewhere)
    manager = await factories.make_staff(session, venue, group, role_slug="manager")
    await factories.grant(session, "manager", MENU_EDIT)

    response = await api_client.patch(
        f"/api/v1/venue/menu/items/{item.id}",
        params={"venue_id": venue.id},
        json={"name": "Boshqa nom"},
        headers=auth_header(manager.user_id),
    )

    assert response.status_code == 404


async def test_waiter_cannot_edit_a_dish(api_client: AsyncClient, session: AsyncSession) -> None:
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    item = await factories.make_menu_item(session, group)
    await factories.make_menu_branch(session, item, venue)
    waiter = await factories.make_staff(session, venue, group, role_slug="waiter")

    response = await api_client.patch(
        f"/api/v1/venue/menu/items/{item.id}",
        params={"venue_id": venue.id},
        json={"name": "Boshqa nom"},
        headers=auth_header(waiter.user_id),
    )

    assert response.status_code == 403
