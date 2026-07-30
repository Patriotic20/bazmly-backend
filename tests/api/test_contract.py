"""Schema-level guarantees the mobile team's generated client depends on."""

from fastapi.routing import APIRoute
from httpx import AsyncClient

from tests.api.conftest import walk_routes

# Every mutating verb under this prefix must be permission-gated.
STAFF_PREFIX = "/api/v1/venue/"
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Accepting an invitation is the one staff-facing write that cannot be guarded:
# the caller is proving who they are with a temporary password precisely because
# they do not have an employment row yet.
UNGUARDED_STAFF_WRITES = {"/api/v1/venue/staff/invitations/accept"}


def dependency_names(route: APIRoute) -> set[str]:
    """Every callable in the route's resolved dependant tree."""
    names: set[str] = set()
    stack = [route.dependant]
    while stack:
        current = stack.pop()
        if current.call is not None:
            names.add(getattr(current.call, "__name__", ""))
            qualname = getattr(current.call, "__qualname__", "")
            if qualname:
                names.add(qualname)
        stack.extend(current.dependencies)
    return names


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
        if "dependency" not in dependency_names(route):
            unguarded.append(f"{sorted(route.methods or set())[0]} {path}")

    assert unguarded == []


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
