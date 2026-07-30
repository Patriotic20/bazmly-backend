from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["version"]


async def test_health_echoes_request_id(client: AsyncClient) -> None:
    response = await client.get("/api/health", headers={"X-Request-ID": "test-request-id"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-id"


async def test_docs_render(client: AsyncClient) -> None:
    response = await client.get("/api/docs")

    assert response.status_code == 200


async def test_unknown_route_uses_the_error_envelope(client: AsyncClient) -> None:
    """One flat body for every error: code, message, details, request_id."""
    response = await client.get("/api/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "http_error"
    assert "message" in body
    assert "request_id" in body


async def test_openapi_exposes_both_customer_and_staff_trees(client: AsyncClient) -> None:
    paths = (await client.get("/api/openapi.json")).json()["paths"]

    assert any(p.startswith("/api/v1/venues") for p in paths)
    assert any(p.startswith("/api/v1/venue/") for p in paths)
