from fastapi import APIRouter, status

from app.core.dependencies import CurrentUser, PendingUser
from app.modules.auth.api.dependencies import AuthServiceDep, UserServiceDep
from app.modules.auth.api.tokens import with_access_token
from app.modules.auth.schemas import (
    PasswordChange,
    PhoneCheck,
    PhoneCheckResult,
    PhoneLogin,
    PhoneRegister,
    RefreshRequest,
    StaffLogin,
    TelegramContactShare,
    TelegramLogin,
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
    "/telegram",
    response_model=TokenPair,
    operation_id="auth_telegram_login",
    summary="Telegram orqali kirish",
    description=(
        "Mini App uchun. Telegram bergan `initData` satri o'zgartirilmagan holda "
        "yuboriladi; imzo tekshirilgach, akkaunt topiladi yoki yaratiladi. "
        "Parol ham, tasdiqlash kodi ham talab qilinmaydi."
    ),
)
async def telegram_login(payload: TelegramLogin, service: AuthServiceDep) -> TokenPair:
    return with_access_token(await service.telegram_login(payload))


@router.post(
    "/telegram/contact",
    response_model=UserRead,
    operation_id="auth_telegram_contact",
    summary="Telegram orqali raqamni tasdiqlash",
    description=(
        "Mini App uchun. `Telegram.WebApp.requestContact` javobi o'zgartirilmagan "
        "holda yuboriladi; imzo tekshirilgach, raqam akkauntga biriktiriladi. "
        "Tasdiqlash kodi yuborilmaydi — raqamni Telegram allaqachon tekshirgan."
    ),
)
async def telegram_contact(
    payload: TelegramContactShare,
    user: CurrentUser,
    service: AuthServiceDep,
) -> UserRead:
    return await service.attach_telegram_contact(user.id, payload)


@router.post(
    "/complete-profile",
    response_model=UserRead,
    operation_id="auth_complete_profile",
    summary="Profilni to'ldirish",
    description=(
        "Ismi kelmagan holda yaratilgan akkauntlar uchun. Ism kiritilgach, "
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
