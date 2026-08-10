"""Region writes are admin-only; region reads stay public for a customer who has
not signed in yet."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import UserRole
from tests.api.conftest import auth_header
from tests.repositories.factories import make_district, make_user


async def test_admin_creates_a_region(api_client: AsyncClient, session: AsyncSession) -> None:
    admin = await make_user(session, role=UserRole.ADMIN)

    response = await api_client.post(
        "/api/v1/regions",
        json={"name": "Namangan", "code": "UZ-NG"},
        headers=auth_header(admin.id),
    )

    assert response.status_code == 201
    assert response.json()["code"] == "UZ-NG"


async def test_customer_cannot_create_a_region(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    customer = await make_user(session, role=UserRole.CUSTOMER)

    response = await api_client.post(
        "/api/v1/regions",
        json={"name": "Namangan", "code": "UZ-NG"},
        headers=auth_header(customer.id),
    )
    assert response.status_code == 403


async def test_admin_updates_a_region(api_client: AsyncClient, session: AsyncSession) -> None:
    admin = await make_user(session, role=UserRole.ADMIN)
    created = await api_client.post(
        "/api/v1/regions",
        json={"name": "Namangan", "code": "UZ-NG"},
        headers=auth_header(admin.id),
    )
    region_id = created.json()["id"]

    response = await api_client.patch(
        f"/api/v1/regions/{region_id}",
        json={"name": "Namangan viloyati"},
        headers=auth_header(admin.id),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Namangan viloyati"
    assert response.json()["code"] == "UZ-NG"


async def test_listing_regions_needs_no_auth(api_client: AsyncClient) -> None:
    """Customers pick a region before they ever sign in."""
    assert (await api_client.get("/api/v1/regions")).status_code == 200


async def test_duplicate_region_code_is_rejected(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await make_user(session, role=UserRole.ADMIN)
    body = {"name": "Namangan", "code": "UZ-NG"}
    assert (
        await api_client.post("/api/v1/regions", json=body, headers=auth_header(admin.id))
    ).status_code == 201

    second = await api_client.post(
        "/api/v1/regions",
        json={"name": "Boshqa", "code": "UZ-NG"},
        headers=auth_header(admin.id),
    )
    assert second.status_code == 422


async def test_deleting_a_region_with_districts_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A raw FK violation would surface as a 500; this must be a validation error."""
    admin = await make_user(session, role=UserRole.ADMIN)
    district = await make_district(session)

    response = await api_client.delete(
        f"/api/v1/regions/{district.region_id}", headers=auth_header(admin.id)
    )

    assert response.status_code == 422
