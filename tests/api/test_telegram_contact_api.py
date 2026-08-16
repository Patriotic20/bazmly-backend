"""Attaching a Telegram-verified phone number to a signed-in account.

There is no code to type: Telegram checked this number when the account was
created, and a valid signature carries that check across. Which makes the
signature, and the `user_id` inside it, the whole of the security — everything
below exists to prove those two are actually enforced.
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.models import User
from tests.api.test_telegram_auth_api import BOT_TOKEN, TELEGRAM_ID, init_data
from tests.test_telegram_init_data import sign

PHONE_DIGITS = "998901112233"
PHONE_E164 = "+998901112233"


@pytest.fixture
def telegram_configured() -> Iterator[None]:
    saved = settings.telegram.bot_token
    settings.telegram.bot_token = BOT_TOKEN
    yield
    settings.telegram.bot_token = saved


def contact_data(
    *,
    user_id: int = TELEGRAM_ID,
    phone_number: str = PHONE_DIGITS,
    bot_token: str = BOT_TOKEN,
) -> str:
    """A `requestContact` response, signed the way Telegram signs one."""
    return sign(
        {
            "contact": json.dumps(
                {"user_id": user_id, "phone_number": phone_number, "first_name": "Aziz"}
            ),
            "auth_date": str(int(datetime.now(UTC).timestamp())),
        },
        bot_token,
    )


async def sign_in(api_client: AsyncClient, telegram_id: int = TELEGRAM_ID) -> dict[str, str]:
    response = await api_client.post(
        "/api/v1/auth/telegram", json={"init_data": init_data(telegram_id)}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_sharing_a_contact_stores_the_number(
    api_client: AsyncClient, session: AsyncSession, telegram_configured: None
) -> None:
    headers = await sign_in(api_client)

    response = await api_client.post(
        "/api/v1/auth/telegram/contact",
        json={"contact_data": contact_data()},
        headers=headers,
    )

    assert response.status_code == 200
    # Telegram sends `998...`; it is stored in the one shape the rest of the API uses.
    assert response.json()["phone"] == PHONE_E164

    stored = await session.execute(select(User.phone).where(User.telegram_id == TELEGRAM_ID))
    assert stored.scalar_one() == PHONE_E164


async def test_a_contact_for_another_account_is_refused(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    """The attack the `user_id` check exists for: a payload captured from one
    person, replayed by another to claim their number."""
    headers = await sign_in(api_client, telegram_id=555_000_111)

    response = await api_client.post(
        "/api/v1/auth/telegram/contact",
        json={"contact_data": contact_data(user_id=TELEGRAM_ID)},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


async def test_a_tampered_number_is_refused(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    """Editing the phone in a genuine payload must not survive the signature."""
    headers = await sign_in(api_client)
    forged = contact_data().replace(PHONE_DIGITS, "998909999999")

    response = await api_client.post(
        "/api/v1/auth/telegram/contact",
        json={"contact_data": forged},
        headers=headers,
    )

    assert response.status_code == 403


async def test_a_payload_signed_by_another_bot_is_refused(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    headers = await sign_in(api_client)

    response = await api_client.post(
        "/api/v1/auth/telegram/contact",
        json={"contact_data": contact_data(bot_token="999:someone-elses-bot")},
        headers=headers,
    )

    assert response.status_code == 403


async def test_a_number_taken_by_someone_else_is_a_conflict(
    api_client: AsyncClient, session: AsyncSession, telegram_configured: None
) -> None:
    """`users.phone` is unique — two accounts cannot claim one number."""
    first = await sign_in(api_client, telegram_id=777_000_001)
    taken = await api_client.post(
        "/api/v1/auth/telegram/contact",
        json={"contact_data": contact_data(user_id=777_000_001)},
        headers=first,
    )
    assert taken.status_code == 200

    second = await sign_in(api_client, telegram_id=777_000_002)
    response = await api_client.post(
        "/api/v1/auth/telegram/contact",
        json={"contact_data": contact_data(user_id=777_000_002)},
        headers=second,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "phone_already_registered"


async def test_a_foreign_number_says_so(api_client: AsyncClient, telegram_configured: None) -> None:
    """A signature that checks out but a number this product cannot serve."""
    headers = await sign_in(api_client)

    response = await api_client.post(
        "/api/v1/auth/telegram/contact",
        json={"contact_data": contact_data(phone_number="79001234567")},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["details"]["reason"] == "phone_not_supported"


async def test_the_endpoint_needs_a_session(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    """There is no account to attach a number to without one."""
    response = await api_client.post(
        "/api/v1/auth/telegram/contact", json={"contact_data": contact_data()}
    )

    assert response.status_code == 401
