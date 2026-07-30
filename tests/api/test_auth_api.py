"""The registration flow end to end, over HTTP."""

import re

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import RefreshToken, User
from tests.api.conftest import RecordingSms

PHONE = "+998901234567"


def code_from(body: str) -> str:
    match = re.search(r"\b(\d{6})\b", body)
    assert match is not None, f"no code in {body!r}"
    return match.group(1)


async def test_request_verify_complete_profile_yields_a_usable_token(
    api_client: AsyncClient, api_sms: RecordingSms, session: AsyncSession
) -> None:
    """The whole happy path, and the token it returns actually authenticates."""
    requested = await api_client.post("/api/v1/auth/request-code", json={"destination": PHONE})
    assert requested.status_code == 200
    assert requested.json()["expires_in_seconds"] == 900

    # No account exists yet — the row appears only once a code verifies.
    count = await session.execute(select(func.count()).select_from(User).where(User.phone == PHONE))
    assert count.scalar_one() == 0

    verified = await api_client.post(
        "/api/v1/auth/verify-code",
        json={"destination": PHONE, "code": code_from(api_sms.last_body_for(PHONE))},
    )
    assert verified.status_code == 200
    tokens = verified.json()
    assert tokens["access_token"] and tokens["refresh_token"]

    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    completed = await api_client.post(
        "/api/v1/auth/complete-profile",
        json={"first_name": "Ali", "last_name": "Valiyev"},
        headers=headers,
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "active"

    # The same token now works on an authenticated read.
    me = await api_client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["first_name"] == "Ali"


async def test_missing_or_bad_token_is_403(api_client: AsyncClient) -> None:
    """`PermissionDeniedError` from the dependency, mapped by the handler — the
    endpoint never raises `HTTPException` itself."""
    assert (await api_client.get("/api/v1/users/me")).status_code == 403

    bad = await api_client.get("/api/v1/users/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 403
    assert bad.json()["code"] == "permission_denied"


async def test_reusing_a_revoked_refresh_token_revokes_the_family(
    api_client: AsyncClient, api_sms: RecordingSms, session: AsyncSession
) -> None:
    """A revoked token in the wild means the family is compromised.

    Rotation revokes the presented token, so replaying it is proof someone kept a
    copy — every token for that user dies, logging out the attacker along with the
    victim.
    """
    await api_client.post("/api/v1/auth/request-code", json={"destination": PHONE})
    verified = await api_client.post(
        "/api/v1/auth/verify-code",
        json={"destination": PHONE, "code": code_from(api_sms.last_body_for(PHONE))},
    )
    first_refresh = verified.json()["refresh_token"]
    user_id = verified.json()["user_id"]

    rotated = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert rotated.status_code == 200
    second_refresh = rotated.json()["refresh_token"]
    assert second_refresh != first_refresh

    # Replaying the rotated-away token is rejected...
    replayed = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert replayed.status_code == 403

    # ...and takes the whole family with it, including the live one.
    live = await session.execute(
        select(func.count())
        .select_from(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
    )
    assert live.scalar_one() == 0

    dead = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": second_refresh})
    assert dead.status_code == 403


@pytest.mark.parametrize("attempt", range(3))
async def test_code_request_is_throttled(
    api_client: AsyncClient, api_sms: RecordingSms, attempt: int
) -> None:
    """Three per ten minutes, then 429."""
    for _ in range(3):
        assert (
            await api_client.post("/api/v1/auth/request-code", json={"destination": PHONE})
        ).status_code == 200

    throttled = await api_client.post("/api/v1/auth/request-code", json={"destination": PHONE})
    assert throttled.status_code == 429
    assert throttled.json()["code"] == "too_many_attempts"
