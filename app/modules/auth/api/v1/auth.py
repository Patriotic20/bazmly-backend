from fastapi import APIRouter, status

from app.core.dependencies import CurrentUser, PendingUser
from app.modules.auth.api.dependencies import AuthServiceDep, UserServiceDep
from app.modules.auth.api.tokens import with_access_token
from app.modules.auth.enums import AuthProvider
from app.modules.auth.schemas import (
    OtpRequest,
    OtpRequested,
    OtpVerify,
    RefreshRequest,
    SocialLogin,
    StaffLogin,
    TokenPair,
    UserProfileUpdate,
    UserRead,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post(
    "/request-code",
    response_model=OtpRequested,
    operation_id="auth_request_code",
    summary="Request an SMS confirmation code",
    description="Sends a 6-digit code. Throttled to three requests per ten minutes.",
)
async def request_code(payload: OtpRequest, service: AuthServiceDep) -> OtpRequested:
    return await service.request_code(payload)


@router.post(
    "/verify-code",
    response_model=TokenPair,
    operation_id="auth_verify_code",
    summary="Verify a confirmation code",
    description="Consumes the code and returns tokens. The account is created here, never earlier.",
)
async def verify_code(payload: OtpVerify, service: AuthServiceDep) -> TokenPair:
    return with_access_token(await service.verify_code(payload))


@router.post(
    "/complete-profile",
    response_model=UserRead,
    operation_id="auth_complete_profile",
    summary="Set the name after verification",
    description="Promotes a pending_profile account to active.",
)
async def complete_profile(
    payload: UserProfileUpdate, user: PendingUser, service: UserServiceDep
) -> UserRead:
    return await service.update_profile(user.id, payload)


@router.post(
    "/social/{provider}",
    response_model=TokenPair,
    operation_id="auth_social_login",
    summary="Sign in with Apple or Google",
    description="Links a new identity to an existing account when the email matches.",
)
async def social_login(
    provider: AuthProvider, payload: SocialLogin, service: AuthServiceDep
) -> TokenPair:
    return with_access_token(
        await service.social_login(payload.model_copy(update={"provider": provider}))
    )


@router.post(
    "/staff-login",
    response_model=TokenPair,
    operation_id="auth_staff_login",
    summary="Sign in with an issued staff login",
    description="Hodimlar sign in with a login and password, not a phone number.",
)
async def staff_login(payload: StaffLogin, service: AuthServiceDep) -> TokenPair:
    return with_access_token(await service.staff_login(payload))


@router.post(
    "/refresh",
    response_model=TokenPair,
    operation_id="auth_refresh",
    summary="Rotate a refresh token",
    description="Reusing a revoked token revokes every token for that user.",
)
async def refresh(payload: RefreshRequest, service: AuthServiceDep) -> TokenPair:
    return with_access_token(await service.refresh(payload.refresh_token))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    operation_id="auth_logout",
    summary="Sign out of this device",
    description="Revokes the presented refresh token.",
)
async def logout(user: CurrentUser, service: AuthServiceDep) -> None:
    await service.logout(user.id)


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    operation_id="auth_logout_all",
    summary="Sign out everywhere",
    description="Revokes every refresh token for the account.",
)
async def logout_all(user: CurrentUser, service: AuthServiceDep) -> None:
    await service.logout(user.id, all_devices=True)
