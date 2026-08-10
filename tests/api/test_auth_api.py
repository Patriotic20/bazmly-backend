"""The sign-in flow end to end, over HTTP."""

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import RefreshToken, User

PHONE = "+998901234567"
PASSWORD = "parol12345"

REGISTER = {"phone": PHONE, "first_name": "Ali", "last_name": "Valiyev"}


async def test_check_then_register_yields_a_usable_token(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The whole happy path, and the token it returns actually authenticates."""
    checked = await api_client.post("/api/v1/auth/phone-check", json={"phone": "901234567"})
    assert checked.status_code == 200
    assert checked.json() == {
        "phone": PHONE,
        "registered": False,
        "password_required": False,
    }

    count = await session.execute(select(func.count()).select_from(User).where(User.phone == PHONE))
    assert count.scalar_one() == 0

    registered = await api_client.post("/api/v1/auth/register", json=REGISTER)
    assert registered.status_code == 201
    tokens = registered.json()
    assert tokens["access_token"] and tokens["refresh_token"]
    assert tokens["profile_completed"] is True

    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = await api_client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["first_name"] == "Ali"
    assert me.json()["status"] == "active"


async def test_registering_a_taken_number_is_409(api_client: AsyncClient) -> None:
    assert (await api_client.post("/api/v1/auth/register", json=REGISTER)).status_code == 201

    again = await api_client.post("/api/v1/auth/register", json=REGISTER)
    assert again.status_code == 409
    assert again.json()["code"] == "phone_already_registered"


async def test_login_requires_the_password_once_one_is_set(api_client: AsyncClient) -> None:
    created = await api_client.post(
        "/api/v1/auth/register", json={**REGISTER, "password": PASSWORD}
    )
    assert created.status_code == 201

    checked = await api_client.post("/api/v1/auth/phone-check", json={"phone": PHONE})
    assert checked.json()["password_required"] is True

    without = await api_client.post("/api/v1/auth/login", json={"phone": PHONE})
    assert without.status_code == 403

    with_it = await api_client.post(
        "/api/v1/auth/login", json={"phone": PHONE, "password": PASSWORD}
    )
    assert with_it.status_code == 200
    assert with_it.json()["user_id"] == created.json()["user_id"]


async def test_a_short_password_is_rejected_in_uzbek(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/auth/register", json={**REGISTER, "password": "qisqa"}
    )
    assert response.status_code == 422
    assert "kamida 8" in str(response.json()["details"])


async def test_setting_a_password_revokes_every_other_session(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    registered = (await api_client.post("/api/v1/auth/register", json=REGISTER)).json()
    headers = {"Authorization": f"Bearer {registered['access_token']}"}

    changed = await api_client.post(
        "/api/v1/auth/password", json={"new_password": PASSWORD}, headers=headers
    )
    assert changed.status_code == 204

    live = await session.execute(
        select(func.count())
        .select_from(RefreshToken)
        .where(
            RefreshToken.user_id == registered["user_id"],
            RefreshToken.revoked_at.is_(None),
        )
    )
    assert live.scalar_one() == 0

    # And the new password is what /login now demands.
    assert (await api_client.post("/api/v1/auth/login", json={"phone": PHONE})).status_code == 403
    signed_in = await api_client.post(
        "/api/v1/auth/login", json={"phone": PHONE, "password": PASSWORD}
    )
    assert signed_in.status_code == 200


async def test_missing_or_bad_token_is_401(api_client: AsyncClient) -> None:
    """`AuthenticationRequiredError` from the dependency, mapped by the handler —
    the endpoint never raises `HTTPException` itself.

    401 rather than 403 because signing in again is exactly what fixes it. A
    caller we *have* identified and still refuse gets a 403, and no amount of
    signing in changes that.
    """
    assert (await api_client.get("/api/v1/users/me")).status_code == 401

    bad = await api_client.get("/api/v1/users/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401
    assert bad.json()["code"] == "unauthenticated"


async def test_reusing_a_revoked_refresh_token_revokes_the_family(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A revoked token in the wild means the family is compromised.

    Rotation revokes the presented token, so replaying it is proof someone kept a
    copy — every token for that user dies, logging out the attacker along with the
    victim.
    """
    registered = (await api_client.post("/api/v1/auth/register", json=REGISTER)).json()
    first_refresh = registered["refresh_token"]
    user_id = registered["user_id"]

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


async def test_logout_kills_only_the_presented_session(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The other device stays signed in — that is the whole difference from
    `/logout-all`, and the old endpoint revoked nothing at all.

    The signed-out token is checked in the database rather than by replaying it at
    `/refresh`: replaying a revoked token is indistinguishable from a leak, so it
    deliberately takes the whole family down and would destroy what this test is
    asserting survives.
    """
    registered = (await api_client.post("/api/v1/auth/register", json=REGISTER)).json()
    headers = {"Authorization": f"Bearer {registered['access_token']}"}
    second_device = (await api_client.post("/api/v1/auth/login", json={"phone": PHONE})).json()

    out = await api_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": registered["refresh_token"]},
        headers=headers,
    )
    assert out.status_code == 204

    live = await session.execute(
        select(func.count())
        .select_from(RefreshToken)
        .where(
            RefreshToken.user_id == registered["user_id"],
            RefreshToken.revoked_at.is_(None),
        )
    )
    assert live.scalar_one() == 1, "exactly the other device's token should remain"

    alive = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": second_device["refresh_token"]}
    )
    assert alive.status_code == 200
