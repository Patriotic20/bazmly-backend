"""Outbound push notifications.

A Protocol with a logging no-op default, so nothing in the domain depends on a
provider SDK and tests can substitute a recorder.

Delivery is deliberately *not* transactional. A dead push token must never roll back
a booking that the database already accepted.
"""

import logging
from typing import Protocol

logger = logging.getLogger("app.transport")


class PushSender(Protocol):
    async def send(self, tokens: list[str], title: str, body: str) -> None: ...


class LoggingPushSender:
    async def send(self, tokens: list[str], title: str, body: str) -> None:
        logger.info("Push queued to %d device(s): %s", len(tokens), title)


_push_sender: PushSender = LoggingPushSender()


def get_push_sender() -> PushSender:
    return _push_sender


def set_push_sender(sender: PushSender) -> None:
    global _push_sender
    _push_sender = sender
