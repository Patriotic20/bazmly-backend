from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import NotFoundError
from app.modules.auth.enums import UserStatus
from app.modules.auth.repositories import RefreshTokenRepository, UserRepository
from app.modules.auth.schemas import UserProfileUpdate, UserRead
from app.modules.reviews.repositories import ReviewRepository


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.tokens = RefreshTokenRepository(session)
        self.reviews = ReviewRepository(session)

    async def get_profile(self, user_id: int) -> UserRead:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Foydalanuvchi topilmadi")
        return UserRead.model_validate(user)

    async def update_profile(self, user_id: int, payload: UserProfileUpdate) -> UserRead:
        """Setting a name promotes `pending_profile` to `active`.

        That transition is the whole point of the two-step registration: the row
        exists from the moment the phone is verified, but the account is not usable
        until the person has identified themselves.
        """
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Foydalanuvchi topilmadi")

        values = payload.model_dump(exclude_unset=True)
        first_name = values.get("first_name", user.first_name)
        last_name = values.get("last_name", user.last_name)
        if user.status == UserStatus.PENDING_PROFILE and first_name.strip() and last_name.strip():
            values["status"] = UserStatus.ACTIVE

        updated = await self.users.update_profile(user_id, values)
        if updated is None:
            raise NotFoundError("Foydalanuvchi topilmadi")
        await self.session.commit()
        return UserRead.model_validate(updated)

    async def delete_account(self, user_id: int) -> None:
        """ "Akkauntni o'chirish" — a soft delete, in one transaction.

        Status and `deleted_at` are set, contact fields and credentials nulled,
        every refresh token revoked and review text anonymised. Bookings and
        orders are deliberately untouched: a hard delete would break financial
        history that the venue and the tax authority both still need.

        The phone is released rather than tombstoned so the number can be used to
        register again; the email becomes a non-routable tombstone because
        `ck_users_phone_or_email` requires one of the two to survive. See
        DECISIONS.md.
        """
        now = utcnow_naive()
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Foydalanuvchi topilmadi")

        await self.tokens.revoke_all_for_user(user_id, now)
        await self.reviews.anonymise_for_user(user_id)
        await self.users.anonymise_and_soft_delete(user_id, now)
        await self.session.commit()
