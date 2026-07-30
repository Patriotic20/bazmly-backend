import hashlib
from datetime import datetime, timedelta
from typing import NoReturn

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import (
    CodeExpiredError,
    InvalidCodeError,
    NotFoundError,
    PermissionDeniedError,
    TooManyAttemptsError,
    ValidationFailedError,
)
from app.core.integrity import translate_integrity_error
from app.core.security import (
    generate_numeric_code,
    generate_token,
    hash_secret,
    verify_secret,
)
from app.core.transports import get_sms_sender
from app.modules.auth.enums import UserRole, UserStatus, VerificationChannel
from app.modules.auth.models import AuthIdentity, RefreshToken, User, VerificationCode
from app.modules.auth.repositories import (
    AuthIdentityRepository,
    RefreshTokenRepository,
    UserRepository,
    VerificationCodeRepository,
)
from app.modules.auth.schemas import (
    OtpRequest,
    OtpRequested,
    OtpVerify,
    SocialLogin,
    StaffLogin,
    TokenPair,
)
from app.modules.localization.repositories import DEFAULT_LANGUAGE_CODE, LanguageRepository

CODE_TTL = timedelta(minutes=15)
THROTTLE_WINDOW = timedelta(minutes=10)
MAX_CODES_PER_WINDOW = 3
MAX_VERIFY_ATTEMPTS = 5

ACCESS_TOKEN_TTL = timedelta(minutes=30)
REFRESH_TOKEN_TTL = timedelta(days=30)


class AuthService:
    """Registration, sign-in and token lifecycle.

    The registration state machine is the load-bearing part: **no `users` row
    exists until a code has been verified**. Creating one at "request code" would
    let anyone mint rows for phone numbers they do not control, and would make
    `users.phone` unique-collide with a number the real owner later tries to use.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.codes = VerificationCodeRepository(session)
        self.tokens = RefreshTokenRepository(session)
        self.identities = AuthIdentityRepository(session)
        self.languages = LanguageRepository(session)

    async def request_code(self, payload: OtpRequest) -> OtpRequested:
        """Throttled at three per ten minutes, per destination and purpose.

        The stored value is a hash; the plaintext exists only long enough to hand
        to the SMS transport and is never logged or returned.
        """
        now = utcnow_naive()
        recent = await self.codes.count_recent(
            payload.destination, payload.purpose, now - THROTTLE_WINDOW
        )
        if recent >= MAX_CODES_PER_WINDOW:
            raise TooManyAttemptsError(
                "Kod juda ko'p so'raldi. Bir necha daqiqadan keyin urinib ko'ring",
                details={"retry_after_seconds": int(THROTTLE_WINDOW.total_seconds())},
            )

        code = generate_numeric_code()
        await self.codes.create(
            VerificationCode(
                channel=payload.channel,
                destination=payload.destination,
                code_hash=hash_secret(code),
                purpose=payload.purpose,
                attempts_count=0,
                expires_at=now + CODE_TTL,
            )
        )
        await self.session.commit()

        if payload.channel == VerificationChannel.SMS:
            await get_sms_sender().send(payload.destination, f"Bazmly tasdiqlash kodi: {code}")

        return OtpRequested(
            destination=payload.destination,
            expires_in_seconds=int(CODE_TTL.total_seconds()),
        )

    async def verify_code(self, payload: OtpVerify) -> TokenPair:
        """Consume a code and issue tokens, creating the user on first success."""
        now = utcnow_naive()
        record = await self.codes.get_active(payload.destination, payload.purpose, now)
        if record is None:
            raise CodeExpiredError()

        if record.attempts_count >= MAX_VERIFY_ATTEMPTS:
            raise TooManyAttemptsError()

        if not verify_secret(payload.code, record.code_hash):
            await self._register_failed_attempt(record.id)

        await self.codes.consume(record.id, now)

        user = await self.users.get_by_phone(payload.destination)
        if user is None:
            user = await self._create_pending_user_in_transaction(payload.destination)

        await self.users.mark_phone_verified(user.id, now)
        await self.users.touch_last_login(user.id, now)
        pair = await self._issue_tokens_in_transaction(user, now)
        await self.session.commit()
        return pair

    async def staff_login(self, payload: StaffLogin) -> TokenPair:
        """Staff authenticate with an issued login, not a phone number."""
        now = utcnow_naive()
        user = await self.users.get_by_login(payload.login)
        if user is None or user.password_hash is None:
            raise PermissionDeniedError("Login yoki parol noto'g'ri")
        if not verify_secret(payload.password, user.password_hash):
            raise PermissionDeniedError("Login yoki parol noto'g'ri")
        if user.status != UserStatus.ACTIVE:
            raise PermissionDeniedError("Bu akkaunt faol emas")

        await self.users.touch_last_login(user.id, now)
        pair = await self._issue_tokens_in_transaction(user, now)
        await self.session.commit()
        return pair

    async def social_login(self, payload: SocialLogin) -> TokenPair:
        """Apple or Google.

        An unknown provider id whose email matches an existing account links a new
        identity to that account rather than creating a second user — otherwise
        signing in with Google after signing up by phone silently forks the
        person's bookings across two rows.
        """
        now = utcnow_naive()
        identity = await self.identities.get_by_provider(payload.provider, payload.provider_user_id)

        if identity is not None:
            user = await self.users.get_by_id(identity.user_id)
            if user is None:
                raise NotFoundError("Bog'langan akkaunt endi mavjud emas")
        else:
            user = None
            if payload.provider_email:
                user = await self.users.get_by_email(payload.provider_email)
            if user is None:
                user = await self._create_social_user_in_transaction(payload)
            await self.identities.create(
                AuthIdentity(
                    user_id=user.id,
                    provider=payload.provider,
                    provider_user_id=payload.provider_user_id,
                    provider_email=payload.provider_email,
                )
            )

        await self.users.touch_last_login(user.id, now)
        pair = await self._issue_tokens_in_transaction(user, now)
        await self.session.commit()
        return pair

    async def refresh(self, refresh_token: str) -> TokenPair:
        now = utcnow_naive()
        stored = await self.tokens.get_by_hash(hash_lookup(refresh_token))

        # TODO(service): family revocation on reuse was added by the API task —
        # see DECISIONS.md.
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

        # Rotation: the presented token dies as the replacement is minted, so a
        # stolen token is usable at most once and its reuse is detectable.
        await self.tokens.revoke(stored.id, now)
        pair = await self._issue_tokens_in_transaction(user, now)
        await self.session.commit()
        return pair

    async def logout(self, user_id: int, all_devices: bool = False) -> None:
        now = utcnow_naive()
        if all_devices:
            await self.tokens.revoke_all_for_user(user_id, now)
        await self.session.commit()

    # --- internals -----------------------------------------------------------

    async def _register_failed_attempt(self, code_id: int) -> NoReturn:
        """Persist the attempt, then raise.

        The commit is not optional: raising without it would roll the increment
        back, the counter would never advance and the five-attempt lockout would
        never fire — an attacker could guess indefinitely.
        """
        attempts = await self.codes.increment_attempts(code_id)
        await self.session.commit()
        if attempts is not None and attempts >= MAX_VERIFY_ATTEMPTS:
            raise TooManyAttemptsError()
        raise InvalidCodeError()

    async def _create_pending_user_in_transaction(self, phone: str) -> User:
        """First successful verification. `pending_profile` until a name is set."""
        language = await self.languages.get_by_code(DEFAULT_LANGUAGE_CODE)
        if language is None:
            raise ValidationFailedError("Asosiy til sozlanmagan")
        try:
            return await self.users.create(
                User(
                    first_name="",
                    last_name="",
                    phone=phone,
                    language_id=language.id,
                    role=UserRole.CUSTOMER,
                    status=UserStatus.PENDING_PROFILE,
                    must_change_password=False,
                )
            )
        except IntegrityError as error:
            raise translate_integrity_error(error) from error

    async def _create_social_user_in_transaction(self, payload: SocialLogin) -> User:
        language = await self.languages.get_by_code(DEFAULT_LANGUAGE_CODE)
        if language is None:
            raise ValidationFailedError("Asosiy til sozlanmagan")
        has_name = bool(payload.first_name)
        try:
            return await self.users.create(
                User(
                    first_name=payload.first_name or "",
                    last_name=payload.last_name or "",
                    email=payload.provider_email,
                    language_id=language.id,
                    role=UserRole.CUSTOMER,
                    status=UserStatus.ACTIVE if has_name else UserStatus.PENDING_PROFILE,
                    must_change_password=False,
                )
            )
        except IntegrityError as error:
            raise translate_integrity_error(error) from error

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
        )


def hash_lookup(token: str) -> str:
    """Deterministic hash for refresh tokens, which must be *looked up* by value.

    `hash_secret` salts per call, so the same token hashes differently every time
    and could never be found again. Refresh tokens are high-entropy random strings
    rather than user-chosen passwords, so a plain digest is not brute-forceable and
    keeps the lookup possible.
    """
    return hashlib.sha256(token.encode()).hexdigest()
