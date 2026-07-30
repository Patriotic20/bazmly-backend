"""Service tests run against a real Postgres with the migrations applied.

Only the SMS and push transports are mocked — they are the two collaborators that
reach outside the process. Everything else is exercised for real, because the
rules under test are enforced by constraints, partial indexes and locks that a
fake would have to reimplement.

Fixtures are reused from `tests/repositories/conftest.py`, which already provides
`engine`, `session` (rolled back per test) and `committing_sessions`.
"""

from collections.abc import AsyncGenerator, Iterator

import pytest

from app.core import transports


class RecordingSmsSender:
    """Captures what would have been sent.

    The plaintext of a code or a temporary password exists only in transit, so a
    test that needs it has to intercept it here — there is nowhere else to read it
    from, which is the property being relied on.
    """

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def send(self, phone: str, body: str) -> str | None:
        self.messages.append((phone, body))
        return "test-message-id"

    def last_body_for(self, phone: str) -> str:
        for sent_phone, body in reversed(self.messages):
            if sent_phone == phone:
                return body
        raise AssertionError(f"No SMS was sent to {phone}")


class RecordingPushSender:
    def __init__(self) -> None:
        self.sent: list[tuple[list[str], str, str]] = []

    async def send(self, tokens: list[str], title: str, body: str) -> None:
        self.sent.append((tokens, title, body))


@pytest.fixture
def sms() -> Iterator[RecordingSmsSender]:
    sender = RecordingSmsSender()
    transports.set_sms_sender(sender)
    yield sender
    transports.set_sms_sender(transports.LoggingSmsSender())


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
