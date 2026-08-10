"""Schema-level guarantees the mobile team's generated client depends on."""

from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.core.dependencies import GroupPermissionRequired, PermissionRequired
from tests.api.conftest import walk_routes

GUARDS = (PermissionRequired, GroupPermissionRequired)

# Every mutating verb under this prefix must be permission-gated.
STAFF_PREFIX = "/api/v1/venue/"
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Two staff-facing writes cannot be guarded, both for the same reason: they run
# before the caller has an employment row, which is what every guard reads.
#
# Accepting an invitation proves identity with a temporary password instead.
# Creating a chain is the bootstrap itself — it is what writes the owner's first
# employment row, so there is nothing to check against. One chain per owner
# stands in for the guard there.
UNGUARDED_STAFF_WRITES = {
    "/api/v1/venue/staff/invitations/accept",
    "/api/v1/venue/groups",
}


def guard_slugs(route: APIRoute) -> set[str]:
    """Every permission slug the route's resolved dependant tree enforces.

    Matches on the guard's type rather than on a callable's name: a name test
    passes for anything that happens to be called `dependency`, and it cannot say
    *which* permission was demanded.
    """
    slugs: set[str] = set()
    stack = [route.dependant]
    while stack:
        current = stack.pop()
        if isinstance(current.call, GUARDS):
            slugs.add(current.call.slug)
        stack.extend(current.dependencies)
    return slugs


def test_operation_ids_are_unique() -> None:
    """The client generator names methods after these; a collision silently drops
    one endpoint from the SDK."""
    operation_ids = [route.operation_id or "" for _, route in walk_routes()]

    assert all(operation_ids), "every route needs an explicit operation_id"
    duplicates = sorted({o for o in operation_ids if operation_ids.count(o) > 1})
    assert duplicates == []


def test_every_route_declares_response_model_summary_and_description() -> None:
    missing: list[str] = []
    for path, route in walk_routes():
        if not route.summary:
            missing.append(f"{path}: summary")
        if not route.description:
            missing.append(f"{path}: description")
        if route.response_model is None and route.status_code != 204:
            missing.append(f"{path}: response_model")

    assert missing == []


def test_every_staff_write_is_permission_guarded() -> None:
    """Walks the dependant tree rather than trusting the decorator by eye.

    A staff write that forgets its guard is not a visible bug — it works, for
    everyone.
    """
    unguarded: list[str] = []
    for path, route in walk_routes():
        if not path.startswith(STAFF_PREFIX):
            continue
        if not ((route.methods or set()) & WRITE_METHODS):
            continue
        if path in UNGUARDED_STAFF_WRITES:
            continue
        if not guard_slugs(route):
            unguarded.append(f"{sorted(route.methods or set())[0]} {path}")

    assert unguarded == []


def test_every_guard_demands_a_seeded_permission() -> None:
    """A slug typo is silent: `VenueStaffRepository.has_permission` joins on the
    string, finds nothing and refuses everyone, which reads exactly like a missing
    role assignment."""
    seeded = {
        "branch.manage",
        "branch.create",
        "staff.manage",
        "menu.edit",
        "menu.publish",
        "orders.open",
        "orders.add_items",
        "orders.close",
        "orders.discount",
        "bookings.confirm",
        "bookings.cancel",
        "reports.view",
        "settings.edit",
    }
    used = {slug for _, route in walk_routes() for slug in guard_slugs(route)}

    assert used - seeded == set()


async def test_openapi_has_no_auto_generated_response_placeholders(
    api_client: AsyncClient,
) -> None:
    """FastAPI invents `Response ...` models when a route omits `response_model`.

    They generate as anonymous types in the client SDK, so their absence is the
    check that every route declared one.
    """
    spec = (await api_client.get("/api/openapi.json")).json()
    schemas = spec.get("components", {}).get("schemas", {})

    placeholders = [name for name in schemas if name.startswith("Response ")]
    assert placeholders == []
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "Bazmly API"


async def test_customer_and_staff_trees_are_separate(api_client: AsyncClient) -> None:
    """Two audiences, two route trees — never one endpoint branching on role."""
    paths = (await api_client.get("/api/openapi.json")).json()["paths"]

    assert "/api/v1/venues/search" in paths
    assert "/api/v1/venue/venues" in paths
    assert "/api/v1/bookings" in paths
    assert "/api/v1/venue/bookings" in paths


async def test_openapi_declares_a_bearer_security_scheme(client: AsyncClient) -> None:
    """The generated mobile client reads auth off `securitySchemes`.

    A raw `authorization` header param would instead surface as an optional string
    field, which reads as "this endpoint is public" and silently produces an SDK
    that never sends the token.
    """
    schema = (await client.get("/api/openapi.json")).json()

    schemes = schema["components"]["securitySchemes"]
    assert any(
        value.get("type") == "http" and value.get("scheme") == "bearer"
        for value in schemes.values()
    ), f"no HTTP bearer scheme in {sorted(schemes)}"


async def test_protected_route_references_the_scheme_not_a_header(client: AsyncClient) -> None:
    """`GET /api/v1/venue/groups/me` is owner-only and must document itself as such."""
    schema = (await client.get("/api/openapi.json")).json()
    operation = schema["paths"]["/api/v1/venue/groups/me"]["get"]

    assert operation.get("security"), "protected route declares no security requirement"
    parameter_names = {p["name"] for p in operation.get("parameters", [])}
    assert "authorization" not in parameter_names, (
        "auth is still a plain header parameter; Swagger will render a text box"
    )
