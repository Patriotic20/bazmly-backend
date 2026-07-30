"""The registration state machine, which is the reason AuthService exists."""

import re

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidCodeError, TooManyAttemptsError
from app.modules.auth.enums import UserStatus, VerificationPurpose
from app.modules.auth.models import User
from app.modules.auth.schemas import OtpRequest, OtpVerify
from app.modules.auth.services import AuthService
from tests.services.conftest import RecordingSmsSender

PHONE = "+998901234567"


def code_from(body: str) -> str:
    match = re.search(r"\b(\d{6})\b", body)
    assert match is not None, f"No 6-digit code in {body!r}"
    return match.group(1)


async def count_users(session: AsyncSession, phone: str) -> int:
    result = await session.execute(
        select(func.count()).select_from(User).where(User.phone == phone)
    )
    return int(result.scalar_one())


async def test_no_user_row_exists_before_the_code_is_verified(
    session: AsyncSession, sms: RecordingSmsSender
) -> None:
    """Requesting a code must not create an account.

    If it did, anyone could mint rows for numbers they do not control and collide
    with `users.phone` when the real owner later signs up.
    """
    service = AuthService(session)

    await service.request_code(OtpRequest(destination=PHONE))

    assert await count_users(session, PHONE) == 0
    assert sms.messages, "A code should have been sent"

    code = code_from(sms.last_body_for(PHONE))
    await service.verify_code(OtpVerify(destination=PHONE, code=code))

    assert await count_users(session, PHONE) == 1


async def test_verified_user_starts_in_pending_profile(
    session: AsyncSession, sms: RecordingSmsSender
) -> None:
    """Verification proves the phone, not the person. A name promotes to active."""
    service = AuthService(session)
    await service.request_code(OtpRequest(destination=PHONE))
    code = code_from(sms.last_body_for(PHONE))

    pair = await service.verify_code(OtpVerify(destination=PHONE, code=code))

    user = await session.get(User, pair.user_id)
    assert user is not None
    assert user.status == UserStatus.PENDING_PROFILE
    assert user.phone_verified_at is not None


async def test_throttle_fires_on_the_fourth_request_in_ten_minutes(
    session: AsyncSession, sms: RecordingSmsSender
) -> None:
    service = AuthService(session)
    payload = OtpRequest(destination=PHONE)

    for _ in range(3):
        await service.request_code(payload)

    with pytest.raises(TooManyAttemptsError):
        await service.request_code(payload)

    assert len(sms.messages) == 3, "The throttled request must not send an SMS"


async def test_five_wrong_codes_locks_out(session: AsyncSession, sms: RecordingSmsSender) -> None:
    """The attempt counter is incremented atomically on every failure, so the
    lockout cannot be sidestepped by racing two guesses."""
    service = AuthService(session)
    await service.request_code(OtpRequest(destination=PHONE))
    real_code = code_from(sms.last_body_for(PHONE))
    wrong = "000000" if real_code != "000000" else "111111"

    for _ in range(4):
        with pytest.raises(InvalidCodeError):
            await service.verify_code(OtpVerify(destination=PHONE, code=wrong))

    # The fifth failure trips the lockout rather than reporting a wrong code.
    with pytest.raises(TooManyAttemptsError):
        await service.verify_code(OtpVerify(destination=PHONE, code=wrong))

    # And the correct code no longer helps.
    with pytest.raises(TooManyAttemptsError):
        await service.verify_code(OtpVerify(destination=PHONE, code=real_code))

    assert await count_users(session, PHONE) == 0


async def test_a_consumed_code_cannot_be_replayed(
    session: AsyncSession, sms: RecordingSmsSender
) -> None:
    service = AuthService(session)
    await service.request_code(OtpRequest(destination=PHONE, purpose=VerificationPurpose.LOGIN))
    code = code_from(sms.last_body_for(PHONE))

    await service.verify_code(
        OtpVerify(destination=PHONE, code=code, purpose=VerificationPurpose.LOGIN)
    )

    from app.core.exceptions import CodeExpiredError

    with pytest.raises(CodeExpiredError):
        await service.verify_code(
            OtpVerify(destination=PHONE, code=code, purpose=VerificationPurpose.LOGIN)
        )
