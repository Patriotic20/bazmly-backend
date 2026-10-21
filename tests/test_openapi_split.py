"""The audience split of the documentation.

One app, one route table — but a frontend developer builds either the admin
panel or the customer app, and their Swagger must show their half plus the
shared sign-in and reference routes. These tests pin the cut: nothing moves
between audiences by accident, and no route silently falls out of both views.
"""

from typing import Any

from httpx import AsyncClient

from app.core.openapi import INTERNAL_TAGS

ADMIN_SCHEMA = "/api/openapi-admin.json"
APP_SCHEMA = "/api/openapi-app.json"


async def paths_of(client: AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(url)
    assert response.status_code == 200
    return dict(response.json()["paths"])


async def test_both_docs_pages_render(client: AsyncClient) -> None:
    for url in ("/api/docs/admin", "/api/docs/app"):
        response = await client.get(url)
        assert response.status_code == 200
        assert "swagger" in response.text.lower()


async def test_the_admin_schema_carries_the_venue_tree_and_not_the_customer_one(
    client: AsyncClient,
) -> None:
    paths = await paths_of(client, ADMIN_SCHEMA)

    assert any(p.startswith("/api/v1/venue/bookings") for p in paths)
    assert any(p.startswith("/api/v1/venue/staff") for p in paths)
    assert not any(p.startswith("/api/v1/bookings") for p in paths)
    assert not any(p.startswith("/api/v1/reviews") for p in paths)


async def test_the_app_schema_carries_the_customer_tree_and_not_the_venue_one(
    client: AsyncClient,
) -> None:
    paths = await paths_of(client, APP_SCHEMA)

    assert any(p.startswith("/api/v1/bookings") for p in paths)
    assert any(p.startswith("/api/v1/venues") for p in paths)
    assert not any(p.startswith("/api/v1/venue/") for p in paths)


async def test_sign_in_and_reference_data_are_in_both(client: AsyncClient) -> None:
    """Both apps sign in through the same endpoints — hiding them helps nobody."""
    admin = await paths_of(client, ADMIN_SCHEMA)
    app_ = await paths_of(client, APP_SCHEMA)

    for paths in (admin, app_):
        assert any(p.startswith("/api/v1/auth") for p in paths)
        assert any(p.startswith("/api/v1/regions") for p in paths)


async def test_the_webhook_is_in_neither_filtered_view(client: AsyncClient) -> None:
    """Telegram talks to it, not a browser — it stays in the full schema only."""
    full = await paths_of(client, "/api/openapi.json")
    admin = await paths_of(client, ADMIN_SCHEMA)
    app_ = await paths_of(client, APP_SCHEMA)

    webhook = "/api/v1/telegram/webhook"
    assert webhook in full
    assert webhook not in admin
    assert webhook not in app_
    # The Telegram *sign-in* routes are auth, not the webhook — they stay shared.
    assert "/api/v1/auth/telegram" in admin
    assert "/api/v1/auth/telegram" in app_


async def test_every_route_lands_in_at_least_one_view(client: AsyncClient) -> None:
    """The failure this guards against is silent: a new endpoint whose tag fits
    neither rule would be documented nowhere, and nobody would notice until a
    frontend developer asks where it went."""
    full = await paths_of(client, "/api/openapi.json")
    admin = await paths_of(client, ADMIN_SCHEMA)
    app_ = await paths_of(client, APP_SCHEMA)

    for path, operations in full.items():
        for method, operation in operations.items():
            if set(operation.get("tags", [])) & INTERNAL_TAGS:
                continue
            assert method in admin.get(path, {}) or method in app_.get(path, {}), (
                f"{method.upper()} {path} is documented in neither audience view"
            )


async def test_the_split_prices_operation_moved_with_its_new_tag(client: AsyncClient) -> None:
    """The one operation reclassified by this change: setting a price is staff work."""
    admin = await paths_of(client, ADMIN_SCHEMA)
    app_ = await paths_of(client, APP_SCHEMA)

    assert "post" in admin.get("/api/v1/venue/services", {})
    assert "/api/v1/venue/services" not in app_
    assert "/api/v1/service-catalog" in app_  # the catalog stays customer-visible


async def test_each_view_names_its_audience(client: AsyncClient) -> None:
    admin_info = (await client.get(ADMIN_SCHEMA)).json()["info"]
    app_info = (await client.get(APP_SCHEMA)).json()["info"]

    assert admin_info["title"] == "Bazmly Admin API"
    assert app_info["title"] == "Bazmly Customer API"


async def test_filtering_does_not_truncate_the_full_schema(client: AsyncClient) -> None:
    """The filter must copy, not trim in place — FastAPI caches and serves the original."""
    before = await paths_of(client, "/api/openapi.json")
    await client.get(ADMIN_SCHEMA)
    await client.get(APP_SCHEMA)
    after = await paths_of(client, "/api/openapi.json")

    assert before == after
