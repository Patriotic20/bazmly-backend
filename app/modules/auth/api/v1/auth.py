from fastapi import APIRouter, status

from app.core.dependencies import CurrentUser, PendingUser
from app.modules.auth.api.dependencies import AuthServiceDep, UserServiceDep
from app.modules.auth.api.tokens import with_access_token
from app.modules.auth.schemas import (
    GoogleLogin,
    PasswordChange,
    PhoneCheck,
    PhoneCheckResult,
    PhoneLogin,
    PhoneRegister,
    RefreshRequest,
    StaffLogin,
    TokenPair,
    UserProfileUpdate,
    UserRead,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post(
    "/phone-check",
    response_model=PhoneCheckResult,
    operation_id="auth_phone_check",
    summary="Telefon raqamini tekshirish",
    description=(
        "Kirishning birinchi qadami. Raqam ro'yxatdan o'tgan bo'lsa `login`, "
        "aks holda `register` ekrani ko'rsatiladi. Token qaytarilmaydi."
    ),
)
async def phone_check(payload: PhoneCheck, service: AuthServiceDep) -> PhoneCheckResult:
    return await service.check_phone(payload)


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    operation_id="auth_register",
    summary="Ro'yxatdan o'tish",
    description=(
        "Telefon raqamdan keyingi qadam: ism va qolgan ma'lumot. Parol ixtiyoriy — "
        "berilsa, keyingi kirishlarda talab qilinadi."
    ),
)
async def register(payload: PhoneRegister, service: AuthServiceDep) -> TokenPair:
    return with_access_token(await service.register(payload))


@router.post(
    "/login",
    response_model=TokenPair,
    operation_id="auth_login",
    summary="Telefon raqami bilan kirish",
    description="Akkauntda parol o'rnatilgan bo'lsa, `password` majburiy.",
)
async def login(payload: PhoneLogin, service: AuthServiceDep) -> TokenPair:
    return with_access_token(await service.login(payload))


@router.post(
    "/social/google",
    response_model=TokenPair,
    operation_id="auth_google_login",
    summary="Google orqali kirish",
    description=(
        "Google bergan `id_token` server tomonida tekshiriladi. Email Google "
        "tomonidan tasdiqlangan bo'lsa, mavjud akkauntga bog'lanadi — ikkinchi "
        "akkaunt yaratilmaydi."
    ),
)
async def google_login(payload: GoogleLogin, service: AuthServiceDep) -> TokenPair:
    return with_access_token(await service.google_login(payload))


@router.post(
    "/complete-profile",
    response_model=UserRead,
    operation_id="auth_complete_profile",
    summary="Profilni to'ldirish",
    description=(
        "Google orqali kirgan va ismi kelmagan akkauntlar uchun. Ism kiritilgach, "
        "akkaunt `pending_profile` dan `active` ga o'tadi."
    ),
)
async def complete_profile(
    payload: UserProfileUpdate, user: PendingUser, service: UserServiceDep
) -> UserRead:
    return await service.update_profile(user.id, payload)


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    operation_id="auth_set_password",
    summary="Parol o'rnatish yoki o'zgartirish",
    description=(
        "Parol allaqachon bor bo'lsa `current_password` majburiy. Parol "
        "o'zgargach, boshqa barcha qurilmalardagi sessiyalar bekor qilinadi."
    ),
)
async def set_password(payload: PasswordChange, user: CurrentUser, service: AuthServiceDep) -> None:
    await service.set_password(user.id, payload)


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
    description="Yuborilgan yangilash tokeni bekor qilinadi — faqat shu qurilma.",
)
async def logout(payload: RefreshRequest, user: CurrentUser, service: AuthServiceDep) -> None:
    await service.logout(user.id, payload.refresh_token)


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    operation_id="auth_logout_all",
    summary="Hamma qurilmadan chiqish",
    description="Akkauntning barcha yangilash tokenlari bekor qilinadi.",
)
async def logout_all(user: CurrentUser, service: AuthServiceDep) -> None:
    await service.logout_all(user.id)
