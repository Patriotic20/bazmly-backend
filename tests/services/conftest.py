"""Service tests run against a real Postgres with the migrations applied.

Only the push transport is mocked — it is the one collaborator that reaches
outside the process. Everything else is exercised for real, because the
rules under test are enforced by constraints, partial indexes and locks that a
fake would have to reimplement.

Fixtures are reused from `tests/repositories/conftest.py`, which already provides
`engine`, `session` (rolled back per test) and `committing_sessions`.
"""

from collections.abc import AsyncGenerator, Iterator

import pytest

from app.core import transports


class RecordingPushSender:
    def __init__(self) -> None:
        self.sent: list[tuple[list[str], str, str]] = []

    async def send(self, tokens: list[str], title: str, body: str) -> None:
        self.sent.append((tokens, title, body))


@pytest.fixture
def push() -> Iterator[RecordingPushSender]:
    sender = RecordingPushSender()
    transports.set_push_sender(sender)
    yield sender
    transports.set_push_sender(transports.LoggingPushSender())


@pytest.fixture
async def fresh_cache() -> AsyncGenerator[None]:
    """A clean availability cache per test, so one test's writes cannot satisfy
    another's read."""
    from app.core.cache import InMemoryAvailabilityCache, set_availability_cache

    set_availability_cache(InMemoryAvailabilityCache())
    yield
    set_availability_cache(InMemoryAvailabilityCache())
