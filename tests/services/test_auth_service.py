"""The registration and sign-in rules, which are the reason AuthService exists."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PermissionDeniedError, PhoneAlreadyRegisteredError
from app.modules.auth.enums import UserStatus
from app.modules.auth.models import User
from app.modules.auth.schemas import PhoneCheck, PhoneLogin, PhoneRegister
from app.modules.auth.services import AuthService

PHONE = "+998901234567"
PASSWORD = "parol12345"


async def count_users(session: AsyncSession, phone: str) -> int:
    result = await session.execute(
        select(func.count()).select_from(User).where(User.phone == phone)
    )
    return int(result.scalar_one())


def register_payload(**overrides: object) -> PhoneRegister:
    return PhoneRegister.model_validate(
        {"phone": PHONE, "first_name": "Ali", "last_name": "Valiyev", **overrides}
    )


async def test_the_same_number_in_three_formats_is_one_account(session: AsyncSession) -> None:
    """Normalisation happens in the schema type, so every entry point shares it.

    Without it `901234567` and `+998901234567` would be two accounts, and the
    second registration would succeed instead of colliding.
    """
    service = AuthService(session)
    await service.register(register_payload())

    for typed in ("901234567", "998901234567", "+998 90 123-45-67"):
        result = await service.check_phone(PhoneCheck.model_validate({"phone": typed}))
        assert result.registered, typed
        assert result.phone == PHONE

    assert await count_users(session, PHONE) == 1


async def test_registering_makes_the_account_active_immediately(session: AsyncSession) -> None:
    """The name arrives with the request, so there is nothing left to complete."""
    service = AuthService(session)

    pair = await service.register(register_payload())

    user = await session.get(User, pair.user_id)
    assert user is not None
    assert user.status == UserStatus.ACTIVE
    assert user.password_hash is None
    assert pair.profile_completed is True


async def test_a_taken_number_cannot_be_registered_twice(session: AsyncSession) -> None:
    service = AuthService(session)
    await service.register(register_payload())

    with pytest.raises(PhoneAlreadyRegisteredError):
        await service.register(register_payload(first_name="Vali"))


async def test_an_account_without_a_password_signs_in_on_the_phone_alone(
    session: AsyncSession,
) -> None:
    service = AuthService(session)
    registered = await service.register(register_payload())

    check = await service.check_phone(PhoneCheck.model_validate({"phone": PHONE}))
    assert check.registered is True
    assert check.password_required is False

    pair = await service.login(PhoneLogin.model_validate({"phone": PHONE}))
    assert pair.user_id == registered.user_id


async def test_a_password_set_at_registration_is_then_required(session: AsyncSession) -> None:
    service = AuthService(session)
    await service.register(register_payload(password=PASSWORD))

    check = await service.check_phone(PhoneCheck.model_validate({"phone": PHONE}))
    assert check.password_required is True

    # Omitting it is not the same as being allowed in without one.
    with pytest.raises(PermissionDeniedError):
        await service.login(PhoneLogin.model_validate({"phone": PHONE}))

    with pytest.raises(PermissionDeniedError):
        await service.login(PhoneLogin.model_validate({"phone": PHONE, "password": "boshqa-parol"}))

    pair = await service.login(PhoneLogin.model_validate({"phone": PHONE, "password": PASSWORD}))
    assert pair.user_id > 0


async def test_an_unknown_number_is_refused_the_same_way_a_wrong_password_is(
    session: AsyncSession,
) -> None:
    """Same error either way, so the endpoint is not an account-existence oracle."""
    service = AuthService(session)
    await service.register(register_payload(password=PASSWORD))

    unknown = pytest.raises(PermissionDeniedError)
    with unknown as no_account:
        await service.login(PhoneLogin.model_validate({"phone": "+998911111111"}))
    with pytest.raises(PermissionDeniedError) as wrong_password:
        await service.login(PhoneLogin.model_validate({"phone": PHONE, "password": "xato-parol"}))

    assert str(no_account.value) == str(wrong_password.value)


async def test_a_blocked_account_cannot_sign_in(session: AsyncSession) -> None:
    service = AuthService(session)
    pair = await service.register(register_payload())

    user = await session.get(User, pair.user_id)
    assert user is not None
    user.status = UserStatus.BLOCKED
    await session.flush()

    with pytest.raises(PermissionDeniedError):
        await service.login(PhoneLogin.model_validate({"phone": PHONE}))
