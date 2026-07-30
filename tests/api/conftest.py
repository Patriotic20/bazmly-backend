"""API tests drive the real app over ASGI, with the session dependency overridden.

`get_session` is the only place a session enters a request, so overriding that one
dependency puts every service in the app onto the test's rolled-back transaction —
no other seam is needed, and nothing about the routing, dependency tree or
exception handling is faked.
"""

from collections.abc import AsyncGenerator, Iterator

import pytest
from fastapi.routing import APIRoute, _IncludedRouter
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import transports
from app.core.config import settings
from app.core.database.mixins import utcnow_naive
from app.core.dependencies import get_session
from app.core.security import encode_access_token
from app.main import app


def walk_routes(
    routes: list[object] | None = None, prefix: str = ""
) -> Iterator[tuple[str, APIRoute]]:
    """Flatten the router tree into `(full_path, route)` pairs.

    FastAPI includes sub-routers lazily, so `app.routes` holds wrappers rather than
    the endpoints themselves; the acceptance tests need the real `APIRoute` objects
    to read their dependant trees.
    """
    for route in app.routes if routes is None else routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
        elif isinstance(route, _IncludedRouter):
            context = route.include_context
            yield from walk_routes(list(context.included_router.routes), prefix + context.prefix)


@pytest.fixture
async def api_client(session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """A client whose requests all run inside the test's transaction."""

    async def override_session() -> AsyncGenerator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def auth_header(user_id: int) -> dict[str, str]:
    """A signed access token for `user_id`.

    Minted the same way the auth endpoints mint it, so the tests exercise the real
    decode path rather than a bypass.
    """
    token = encode_access_token(
        user_id,
        settings.security.secret_key,
        utcnow_naive(),
        settings.security.access_token_ttl_minutes,
    )
    return {"Authorization": f"Bearer {token}"}


class RecordingSms:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def send(self, phone: str, body: str) -> str | None:
        self.messages.append((phone, body))
        return "test-id"

    def last_body_for(self, phone: str) -> str:
        for sent_phone, body in reversed(self.messages):
            if sent_phone == phone:
                return body
        raise AssertionError(f"No SMS sent to {phone}")


@pytest.fixture
def api_sms() -> Iterator[RecordingSms]:
    sender = RecordingSms()
    transports.set_sms_sender(sender)
    yield sender
    transports.set_sms_sender(transports.LoggingSmsSender())
