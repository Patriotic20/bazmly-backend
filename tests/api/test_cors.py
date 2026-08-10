"""CORS is the whole connection to the frontend, so it is asserted like a contract.

The browser calls this API directly — there is no proxy in front of it — which
makes these headers load-bearing rather than incidental. A regression here is
invisible from `curl`, invisible from Swagger (same origin), and total from the
frontend: every request fails while every manual check passes.

The origin is read from `settings` rather than hardcoded, so the suite asserts
the mechanism and not one deployment's value.
"""

from httpx import AsyncClient

from app.core.config import CorsConfig, settings

# Any path works — CORS is middleware and runs before routing. This one is the
# cheapest: no database, no auth, always 200.
PROBE_PATH = "/api/openapi.json"


def allowed_origin() -> str:
    """An origin this deployment accepts.

    `["*"]` accepts every origin, and Starlette still echoes the concrete one
    back rather than `*` because `allow_credentials` is on.
    """
    origins = settings.cors.origins
    return "http://localhost:3000" if origins == ["*"] else origins[0]


async def test_preflight_is_answered_for_a_configured_origin(client: AsyncClient) -> None:
    """The browser sends this before any non-simple request and refuses to
    continue without an echo of its own origin."""
    origin = allowed_origin()

    response = await client.options(
        "/api/v1/regions",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


async def test_a_response_carries_the_allowed_origin(client: AsyncClient) -> None:
    response = await client.get(PROBE_PATH, headers={"Origin": allowed_origin()})

    assert response.headers["access-control-allow-origin"] == allowed_origin()


async def test_the_browser_can_read_the_request_id(client: AsyncClient) -> None:
    """`X-Request-ID` is on every response, but a header the server sends is not
    a header the client may read until it is exposed."""
    response = await client.get(PROBE_PATH, headers={"Origin": allowed_origin()})

    exposed = response.headers["access-control-expose-headers"].lower()
    assert "x-request-id" in exposed


def test_the_request_id_is_exposed_by_default() -> None:
    """Asserted on the model default rather than on `settings`, which any local
    `.env` can override: a deployment that configures nothing must still hand the
    id to the client."""
    assert "X-Request-ID" in CorsConfig().expose_headers
