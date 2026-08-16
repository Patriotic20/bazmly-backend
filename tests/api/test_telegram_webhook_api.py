"""The bot's own endpoint — the half of Telegram that is not the Mini App.

Two properties matter here and nothing else does. The secret header is the only
authentication: the URL is guessable, so without it anyone could post a forged
update and have the bot message any chat id they named. And the endpoint must
answer 200 to anything Telegram sends, because a non-2xx is read as "not
delivered" and retried — one bad update would become a backlog.
"""

from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from app.core.config import settings

SECRET = "webhook-secret-for-tests"

START = {
    "update_id": 1,
    "message": {"chat": {"id": 4242}, "text": "/start", "from": {"id": 7}},
}


@pytest.fixture
def webhook_configured() -> Iterator[None]:
    saved = (settings.telegram.webhook_secret, settings.telegram.bot_token)
    settings.telegram.webhook_secret = SECRET
    # Deliberately empty: sending is then refused by Telegram, and the point of
    # these tests is what the endpoint does, not what the reply looks like.
    settings.telegram.bot_token = ""
    yield
    settings.telegram.webhook_secret, settings.telegram.bot_token = saved


async def test_an_update_with_the_secret_is_accepted(
    api_client: AsyncClient, webhook_configured: None
) -> None:
    response = await api_client.post(
        "/api/v1/telegram/webhook",
        json=START,
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )

    assert response.status_code == 200


async def test_an_update_without_the_secret_is_refused(
    api_client: AsyncClient, webhook_configured: None
) -> None:
    """The attack this header exists for: a forged update from anyone at all."""
    response = await api_client.post("/api/v1/telegram/webhook", json=START)

    assert response.status_code == 403


async def test_a_wrong_secret_is_refused(api_client: AsyncClient, webhook_configured: None) -> None:
    response = await api_client.post(
        "/api/v1/telegram/webhook",
        json=START,
        headers={"X-Telegram-Bot-Api-Secret-Token": "guessed"},
    )

    assert response.status_code == 403


async def test_an_unconfigured_secret_refuses_everything(api_client: AsyncClient) -> None:
    """No secret set means the bot is not wired up — it must not accept updates."""
    saved = settings.telegram.webhook_secret
    settings.telegram.webhook_secret = ""
    try:
        response = await api_client.post(
            "/api/v1/telegram/webhook",
            json=START,
            headers={"X-Telegram-Bot-Api-Secret-Token": ""},
        )
    finally:
        settings.telegram.webhook_secret = saved

    assert response.status_code == 403


async def test_an_update_shape_we_do_not_handle_still_returns_200(
    api_client: AsyncClient, webhook_configured: None
) -> None:
    """Telegram sends dozens of update types and adds more over time. An unknown
    one is not an error; treating it as one would make Telegram retry forever."""
    response = await api_client.post(
        "/api/v1/telegram/webhook",
        json={"update_id": 2, "my_chat_member": {"anything": True}},
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )

    assert response.status_code == 200


async def test_an_unknown_command_is_ignored_quietly(
    api_client: AsyncClient, webhook_configured: None
) -> None:
    response = await api_client.post(
        "/api/v1/telegram/webhook",
        json={"update_id": 3, "message": {"chat": {"id": 1}, "text": "salom"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )

    assert response.status_code == 200


async def test_a_reply_failure_does_not_fail_the_delivery(
    api_client: AsyncClient, webhook_configured: None
) -> None:
    """With no bot token the send cannot succeed — Telegram must still be told
    the update arrived, or it will send it again."""
    response = await api_client.post(
        "/api/v1/telegram/webhook",
        json=START,
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )

    assert response.status_code == 200
