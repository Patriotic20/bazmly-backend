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
    summary="Tasdiqlash kodini so'rash",
    description="6 xonali kod yuboriladi. O'n daqiqada uch martadan ko'p so'rab bo'lmaydi.",
)
async def request_code(payload: OtpRequest, service: AuthServiceDep) -> OtpRequested:
    return await service.request_code(payload)


@router.post(
    "/verify-code",
    response_model=TokenPair,
    operation_id="auth_verify_code",
    summary="Tasdiqlash kodini tekshirish",
    description=(
        "Kod ishlatiladi va tokenlar qaytariladi. Akkaunt aynan shu bosqichda "
        "yaratiladi, undan oldin emas."
    ),
)
async def verify_code(payload: OtpVerify, service: AuthServiceDep) -> TokenPair:
    return with_access_token(await service.verify_code(payload))


@router.post(
    "/complete-profile",
    response_model=UserRead,
    operation_id="auth_complete_profile",
    summary="Profilni to'ldirish",
    description="Ism kiritilgach, akkaunt `pending_profile` dan `active` ga o'tadi.",
)
async def complete_profile(
    payload: UserProfileUpdate, user: PendingUser, service: UserServiceDep
) -> UserRead:
    return await service.update_profile(user.id, payload)


@router.post(
    "/social/{provider}",
    response_model=TokenPair,
    operation_id="auth_social_login",
    summary="Apple yoki Google orqali kirish",
    description=(
        "Email mos kelsa, yangi identifikator mavjud akkauntga bog'lanadi — "
        "ikkinchi akkaunt yaratilmaydi."
    ),
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
    summary="Hodim sifatida kirish",
    description="Hodimlar telefon raqami bilan emas, login va parol bilan kiradi.",
)
async def staff_login(payload: StaffLogin, service: AuthServiceDep) -> TokenPair:
    return with_access_token(await service.staff_login(payload))


@router.post(
    "/refresh",
    response_model=TokenPair,
    operation_id="auth_refresh",
    summary="Tokenni yangilash",
    description=(
        "Bekor qilingan token qayta ishlatilsa, o'sha foydalanuvchining barcha "
        "tokenlari bekor qilinadi."
    ),
)
async def refresh(payload: RefreshRequest, service: AuthServiceDep) -> TokenPair:
    return with_access_token(await service.refresh(payload.refresh_token))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    operation_id="auth_logout",
    summary="Chiqish",
    description="Yuborilgan yangilash tokeni bekor qilinadi.",
)
async def logout(user: CurrentUser, service: AuthServiceDep) -> None:
    await service.logout(user.id)


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    operation_id="auth_logout_all",
    summary="Hamma qurilmadan chiqish",
    description="Akkauntning barcha yangilash tokenlari bekor qilinadi.",
)
async def logout_all(user: CurrentUser, service: AuthServiceDep) -> None:
    await service.logout(user.id, all_devices=True)
