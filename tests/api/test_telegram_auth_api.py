"""Telegram Mini App sign-in, over HTTP.

The signature itself is covered in `tests/test_telegram_init_data.py`. What is
asserted here is the half that touches the database: a first arrival creates an
account, a second one finds it again rather than creating a twin, and the token
that comes back authenticates like any other.

`settings.telegram.bot_token` is a process-wide singleton, so every test that
sets it restores it — otherwise the first one to run would configure Telegram
for the whole session.
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.models import User
from tests.test_telegram_init_data import sign

BOT_TOKEN = "123456:test-bot-token"

TELEGRAM_ID = 590_123_456


@pytest.fixture
def telegram_configured() -> Iterator[None]:
    saved = settings.telegram.bot_token
    settings.telegram.bot_token = BOT_TOKEN
    yield
    settings.telegram.bot_token = saved


def init_data(
    telegram_id: int = TELEGRAM_ID,
    *,
    first_name: str = "Aziz",
    last_name: str | None = "Umarov",
    language_code: str | None = None,
) -> str:
    user: dict[str, object] = {"id": telegram_id, "first_name": first_name}
    if last_name is not None:
        user["last_name"] = last_name
    if language_code is not None:
        user["language_code"] = language_code

    return sign(
        {
            "user": json.dumps(user),
            "auth_date": str(int(datetime.now(UTC).timestamp())),
            "query_id": "AAH-test",
        },
        BOT_TOKEN,
    )


async def test_a_first_arrival_creates_an_account_and_signs_in(
    api_client: AsyncClient, session: AsyncSession, telegram_configured: None
) -> None:
    response = await api_client.post("/api/v1/auth/telegram", json={"init_data": init_data()})

    assert response.status_code == 200
    tokens = response.json()
    assert tokens["access_token"] and tokens["refresh_token"]
    # No password screen and no profile screen: Telegram supplied the name.
    assert tokens["must_change_password"] is False
    assert tokens["profile_completed"] is True

    me = await api_client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["first_name"] == "Aziz"
    assert me.json()["status"] == "active"
    # The account exists with no phone at all — the point of the relaxed check.
    assert me.json()["phone"] is None


async def test_a_second_arrival_finds_the_same_account(
    api_client: AsyncClient, session: AsyncSession, telegram_configured: None
) -> None:
    """Opening the Mini App twice must not produce two people."""
    first = await api_client.post("/api/v1/auth/telegram", json={"init_data": init_data()})
    second = await api_client.post("/api/v1/auth/telegram", json={"init_data": init_data()})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["user_id"] == second.json()["user_id"]

    count = await session.execute(
        select(func.count()).select_from(User).where(User.telegram_id == TELEGRAM_ID)
    )
    assert count.scalar_one() == 1


async def test_two_telegram_accounts_are_two_users(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    first = await api_client.post("/api/v1/auth/telegram", json={"init_data": init_data(111)})
    second = await api_client.post("/api/v1/auth/telegram", json={"init_data": init_data(222)})

    assert first.json()["user_id"] != second.json()["user_id"]


async def test_a_missing_surname_is_accepted(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    """Telegram does not require one, so neither can this."""
    response = await api_client.post(
        "/api/v1/auth/telegram", json={"init_data": init_data(333, last_name=None)}
    )

    assert response.status_code == 200


async def test_the_interface_language_follows_telegram(
    api_client: AsyncClient, session: AsyncSession, telegram_configured: None
) -> None:
    """`ru-RU` and `ru` mean the same row; an unknown code falls back to Uzbek."""
    response = await api_client.post(
        "/api/v1/auth/telegram", json={"init_data": init_data(444, language_code="ru-RU")}
    )
    assert response.status_code == 200

    me = await api_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    language = await session.execute(select(User.language_id).where(User.telegram_id == 444))
    assert me.json()["language_id"] == language.scalar_one()


async def test_a_forged_payload_is_refused(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    forged = init_data().replace(str(TELEGRAM_ID), "1")

    response = await api_client.post("/api/v1/auth/telegram", json={"init_data": forged})

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


async def test_telegram_sign_in_is_off_without_a_bot_token(api_client: AsyncClient) -> None:
    """The shipped default configures no bot, and must not accept anything."""
    saved = settings.telegram.bot_token
    settings.telegram.bot_token = ""
    try:
        response = await api_client.post("/api/v1/auth/telegram", json={"init_data": init_data()})
    finally:
        settings.telegram.bot_token = saved

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
