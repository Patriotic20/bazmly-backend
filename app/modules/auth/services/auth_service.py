import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database.mixins import utcnow_naive
from app.core.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    PhoneAlreadyRegisteredError,
    ValidationFailedError,
)
from app.core.integrity import translate_integrity_error
from app.core.security import (
    generate_token,
    hash_secret,
    verify_secret,
)
from app.modules.auth.enums import UserRole, UserStatus
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.repositories import (
    RefreshTokenRepository,
    UserRepository,
)
from app.modules.auth.schemas import (
    PasswordChange,
    PhoneCheck,
    PhoneCheckResult,
    PhoneLogin,
    PhoneRegister,
    StaffLogin,
    TelegramLogin,
    TokenPair,
)
from app.modules.auth.telegram import TelegramUser, parse_init_data
from app.modules.localization.repositories import DEFAULT_LANGUAGE_CODE, LanguageRepository

ACCESS_TOKEN_TTL = timedelta(minutes=30)
REFRESH_TOKEN_TTL = timedelta(days=30)

# The same string for a wrong password and an unknown login, on purpose: telling
# them apart turns the endpoint into a "does this account exist" oracle.
BAD_CREDENTIALS = "Login yoki parol noto'g'ri"


class AuthService:
    """Registration, sign-in and token lifecycle.

    Sign-in starts from a phone number and nothing else. `check_phone` says
    whether that number is known and whether it carries a password, and the
    client sends the person to `register` or to `login` accordingly. A password
    is optional: an account without one is reachable by phone alone, which is the
    trade the product made when it dropped SMS verification.

    Phone numbers arrive already in E.164 — the `PhoneNumber` schema type
    normalises `901234567`, `998901234567` and `+998 90 123-45-67` to the same
    string before this layer sees any of them, so the lookups here cannot miss an
    account because of formatting.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.tokens = RefreshTokenRepository(session)
        self.languages = LanguageRepository(session)

    async def check_phone(self, payload: PhoneCheck) -> PhoneCheckResult:
        """Which of the two next screens the client should show. No token."""
        user = await self.users.get_by_phone(payload.phone)
        return PhoneCheckResult(
            phone=payload.phone,
            registered=user is not None,
            password_required=user is not None and user.password_hash is not None,
        )

    async def register(self, payload: PhoneRegister) -> TokenPair:
        """Create the account and sign in, in one step.

        The name arrives with the request, so the account is `active` immediately.
        """
        now = utcnow_naive()
        existing = await self.users.get_by_phone(payload.phone)
        if existing is not None:
            raise PhoneAlreadyRegisteredError()

        language_id = payload.language_id or await self._default_language_id()
        try:
            user = await self.users.create(
                User(
                    first_name=payload.first_name,
                    last_name=payload.last_name,
                    phone=payload.phone,
                    language_id=language_id,
                    district_id=payload.district_id,
                    role=UserRole.CUSTOMER,
                    status=UserStatus.ACTIVE,
                    password_hash=hash_secret(payload.password) if payload.password else None,
                    must_change_password=False,
                )
            )
        except IntegrityError as error:
            # Two requests for the same new number can both pass the check above;
            # the unique index is what actually decides, and this turns its error
            # into the same 409 the check would have produced.
            raise translate_integrity_error(error) from error

        await self.users.touch_last_login(user.id, now)
        pair = await self._issue_tokens_in_transaction(user, now)
        await self.session.commit()
        return pair

    async def telegram_login(self, payload: TelegramLogin) -> TokenPair:
        """Sign in — or sign up — the Telegram account that opened the Mini App.

        There is no password step and no registration screen, because Telegram
        already proved who this is. `parse_init_data` is the whole trust
        boundary: past it, the id is as good as a verified phone number.

        First arrival creates the account. That is the same trade `register`
        makes — the name comes with the request, so the profile is complete —
        except the account has no phone number. A booking asks for a contact
        number in its own payload, so this does not block one.
        """
        now = utcnow_naive()
        telegram_user = parse_init_data(
            payload.init_data,
            settings.telegram.bot_token,
            now.replace(tzinfo=UTC),
            settings.telegram.init_data_max_age_seconds,
        )

        user = await self.users.get_by_telegram_id(telegram_user.id)
        if user is None:
            user = await self._create_from_telegram(telegram_user)
        else:
            self._require_usable(user)

        await self.users.touch_last_login(user.id, now)
        pair = await self._issue_tokens_in_transaction(user, now)
        await self.session.commit()
        return pair

    async def _create_from_telegram(self, telegram_user: TelegramUser) -> User:
        """Telegram guarantees an id and a first name, and promises nothing else."""
        language = None
        if telegram_user.language_code:
            # `ru-RU` and `ru` both mean the same row; an unknown code is not an
            # error, it just means the interface stays in Uzbek.
            language = await self.languages.get_by_code(telegram_user.language_code[:2].lower())
        language_id = language.id if language else await self._default_language_id()

        try:
            return await self.users.create(
                User(
                    first_name=telegram_user.first_name,
                    last_name=telegram_user.last_name or "",
                    telegram_id=telegram_user.id,
                    avatar_url=telegram_user.photo_url,
                    language_id=language_id,
                    role=UserRole.CUSTOMER,
                    status=UserStatus.ACTIVE,
                    must_change_password=False,
                )
            )
        except IntegrityError as error:
            # Two taps on a cold start race here; the unique index on
            # `telegram_id` is what actually decides which one wins.
            raise translate_integrity_error(error) from error

    async def login(self, payload: PhoneLogin) -> TokenPair:
        """Phone, plus a password only if the account has one."""
        now = utcnow_naive()
        user = await self.users.get_by_phone(payload.phone)
        if user is None:
            raise PermissionDeniedError(BAD_CREDENTIALS)

        if user.password_hash is not None and not (
            payload.password and verify_secret(payload.password, user.password_hash)
        ):
            raise PermissionDeniedError(BAD_CREDENTIALS)

        self._require_usable(user)

        await self.users.touch_last_login(user.id, now)
        pair = await self._issue_tokens_in_transaction(user, now)
        await self.session.commit()
        return pair

    async def staff_login(self, payload: StaffLogin) -> TokenPair:
        """Staff authenticate with an issued login, not a phone number."""
        now = utcnow_naive()
        user = await self.users.get_by_login(payload.login)
        if user is None or user.password_hash is None:
            raise PermissionDeniedError(BAD_CREDENTIALS)
        if not verify_secret(payload.password, user.password_hash):
            raise PermissionDeniedError(BAD_CREDENTIALS)
        if user.status != UserStatus.ACTIVE:
            raise PermissionDeniedError("Bu akkaunt faol emas")

        await self.users.touch_last_login(user.id, now)
        pair = await self._issue_tokens_in_transaction(user, now)
        await self.session.commit()
        return pair

    async def set_password(self, user_id: int, payload: PasswordChange) -> None:
        """Set a first password, or change an existing one.

        Changing requires the current one. Setting the first does not — there is
        nothing to prove, and the bearer token already proves as much as any
        password would.
        """
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Foydalanuvchi topilmadi")

        if user.password_hash is not None and not (
            payload.current_password and verify_secret(payload.current_password, user.password_hash)
        ):
            raise PermissionDeniedError("Joriy parol noto'g'ri")

        now = utcnow_naive()
        await self.users.set_password(user_id, hash_secret(payload.new_password))
        # Every other session dies with the old password. If the change was a
        # response to a compromise, leaving the attacker's refresh token alive
        # would make the change pointless.
        await self.tokens.revoke_all_for_user(user_id, now)
        await self.session.commit()

    async def refresh(self, refresh_token: str) -> TokenPair:
        now = utcnow_naive()
        stored = await self.tokens.get_by_hash(hash_lookup(refresh_token))

        if stored is not None and stored.revoked_at is not None:
            # A revoked token being presented means it leaked: the legitimate
            # holder already rotated past it, so whoever sent this one copied it.
            # Revoking the whole family logs the attacker out along with the
            # victim, which is the only safe reading of the event.
            await self.tokens.revoke_all_for_user(stored.user_id, now)
            await self.session.commit()
            raise PermissionDeniedError("Yangilash tokeni bekor qilingan")

        if stored is None or stored.expires_at <= now:
            raise PermissionDeniedError("Yangilash tokeni yaroqsiz")

        user = await self.users.get_by_id(stored.user_id)
        if user is None:
            raise NotFoundError("Akkaunt endi mavjud emas")
        self._require_usable(user)

        # Rotation: the presented token dies as the replacement is minted, so a
        # stolen token is usable at most once and its reuse is detectable.
        await self.tokens.revoke(stored.id, now)
        pair = await self._issue_tokens_in_transaction(user, now)
        await self.session.commit()
        return pair

    async def logout(self, user_id: int, refresh_token: str) -> None:
        """Revoke the presented refresh token — this device only.

        The token has to be presented: an access token names the user but not the
        session, so without it there is nothing to identify which of the person's
        devices is signing out.
        """
        now = utcnow_naive()
        stored = await self.tokens.get_by_hash(hash_lookup(refresh_token))
        # Someone else's token is not this caller's to revoke.
        if stored is not None and stored.user_id == user_id and stored.revoked_at is None:
            await self.tokens.revoke(stored.id, now)
        await self.session.commit()

    async def logout_all(self, user_id: int) -> None:
        now = utcnow_naive()
        await self.tokens.revoke_all_for_user(user_id, now)
        await self.session.commit()

    # --- internals -----------------------------------------------------------

    @staticmethod
    def _require_usable(user: User) -> None:
        """`pending_profile` may still sign in — completing the profile is the
        next screen, and refusing the token would make it unreachable."""
        if user.status in (UserStatus.BLOCKED, UserStatus.DELETED):
            raise PermissionDeniedError("Bu akkaunt faol emas")

    async def _default_language_id(self) -> int:
        language = await self.languages.get_by_code(DEFAULT_LANGUAGE_CODE)
        if language is None:
            raise ValidationFailedError("Asosiy til sozlanmagan")
        return language.id

    async def _issue_tokens_in_transaction(self, user: User, now: datetime) -> TokenPair:
        refresh_token = generate_token()
        await self.tokens.create(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_lookup(refresh_token),
                expires_at=now + REFRESH_TOKEN_TTL,
            )
        )
        return TokenPair(
            access_token=generate_token(),
            refresh_token=refresh_token,
            expires_in_seconds=int(ACCESS_TOKEN_TTL.total_seconds()),
            user_id=user.id,
            must_change_password=user.must_change_password,
            profile_completed=user.status != UserStatus.PENDING_PROFILE,
        )


def hash_lookup(token: str) -> str:
    """Deterministic hash for refresh tokens, which must be *looked up* by value.

    `hash_secret` salts per call, so the same token hashes differently every time
    and could never be found again. Refresh tokens are high-entropy random strings
    rather than user-chosen passwords, so a plain digest is not brute-forceable and
    keeps the lookup possible.
    """
    return hashlib.sha256(token.encode()).hexdigest()
