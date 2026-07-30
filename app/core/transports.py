"""Outbound side effects: SMS and push.

Protocols with logging no-op defaults, so nothing in the domain depends on a
provider SDK and tests can substitute a recorder. These are the only collaborators
the service tests mock.

Delivery is deliberately *not* transactional. A dead push token or an SMS gateway
timeout must never roll back a booking that the database already accepted.
"""

import logging
from typing import Protocol

logger = logging.getLogger("app.transport")


class SmsSender(Protocol):
    async def send(self, phone: str, body: str) -> str | None:
        """Deliver `body` to `phone`. Returns a provider message id when there is one."""
        ...


class PushSender(Protocol):
    async def send(self, tokens: list[str], title: str, body: str) -> None: ...


class LoggingSmsSender:
    """Default sender. Logs that a message was sent, never what it contained.

    The body carries one-time codes and temporary passwords; logging it would
    persist exactly the secret the hashing elsewhere is designed to avoid storing.
    """

    async def send(self, phone: str, body: str) -> str | None:
        logger.info("SMS queued to %s (%d chars)", phone, len(body))
        return None


class LoggingPushSender:
    async def send(self, tokens: list[str], title: str, body: str) -> None:
        logger.info("Push queued to %d device(s): %s", len(tokens), title)


_sms_sender: SmsSender = LoggingSmsSender()
_push_sender: PushSender = LoggingPushSender()


def get_sms_sender() -> SmsSender:
    return _sms_sender


def get_push_sender() -> PushSender:
    return _push_sender


def set_sms_sender(sender: SmsSender) -> None:
    global _sms_sender
    _sms_sender = sender


def set_push_sender(sender: PushSender) -> None:
    global _push_sender
    _push_sender = sender
