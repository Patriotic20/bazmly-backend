from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User, UserStatus
from app.modules.localization.models import Language


@dataclass(frozen=True, slots=True)
class UserWithLanguage:
    user: User
    language: Language


class UserRepository:
    """Soft-deleted users are invisible to every read but
    `get_by_id_including_deleted`, which accounting and support still need."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_id_including_deleted(self, user_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.phone == phone, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_login(self, login: str) -> User | None:
        """Staff credentials live on `users`, so this is the staff sign-in lookup."""
        result = await self.session.execute(
            select(User).where(User.login == login, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_with_language(self, user_id: int) -> UserWithLanguage | None:
        result = await self.session.execute(
            select(User, Language)
            .join(Language, Language.id == User.language_id)
            .where(User.id == user_id, User.deleted_at.is_(None))
        )
        row = result.one_or_none()
        if row is None:
            return None
        return UserWithLanguage(user=row[0], language=row[1])

    async def exists_by_phone(self, phone: str) -> bool:
        result = await self.session.execute(
            select(select(User.id).where(User.phone == phone, User.deleted_at.is_(None)).exists())
        )
        return bool(result.scalar_one())

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def set_password(self, user_id: int, password_hash: str) -> User | None:
        """Set or replace the password. `must_change_password` clears with it —
        the person has just chosen this one, so there is nothing left to force."""
        result = await self.session.execute(
            update(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .values(password_hash=password_hash, must_change_password=False)
            .returning(User)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def touch_last_login(self, user_id: int, now: datetime) -> None:
        await self.session.execute(update(User).where(User.id == user_id).values(last_login_at=now))
        await self.session.flush()

    async def soft_delete(self, user_id: int, now: datetime) -> User | None:
        """ "Akkauntni o'chirish" — status and timestamp set, identifiers nulled.

        Bookings and orders stay for accounting; a hard delete would break
        financial history. Revoking tokens is the service's job, since those
        live in another aggregate.
        """
        result = await self.session.execute(
            update(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .values(
                status=UserStatus.DELETED,
                deleted_at=now,
                phone=None,
                email=None,
                avatar_url=None,
                login=None,
                password_hash=None,
            )
            .returning(User)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def list_by_ids(self, user_ids: Sequence[int]) -> Sequence[User]:
        if not user_ids:
            return []
        result = await self.session.execute(
            select(User).where(User.id.in_(user_ids), User.deleted_at.is_(None))
        )
        return result.scalars().all()

    async def count_active(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.deleted_at.is_(None))
        )
        return int(result.scalar_one())

    async def update_profile(self, user_id: int, values: dict[str, Any]) -> User | None:
        """Partial profile update. Cannot touch credentials or status by design —
        those transitions have their own methods with their own guards.
        """
        if not values:
            return await self.get_by_id(user_id)
        result = await self.session.execute(
            update(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .values(**values)
            .returning(User)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def set_credentials(
        self, user_id: int, login: str, password_hash: str, must_change_password: bool
    ) -> User | None:
        """Issued by a staff invitation, never chosen at signup."""
        result = await self.session.execute(
            update(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .values(
                login=login,
                password_hash=password_hash,
                must_change_password=must_change_password,
            )
            .returning(User)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def anonymise_and_soft_delete(self, user_id: int, now: datetime) -> User | None:
        """Soft delete that survives `ck_users_phone_or_email`.

        The constraint requires at least one contact field, so `soft_delete` above
        — which nulls both — can never commit. Here the phone is released to NULL
        so the number can be registered again, and the email becomes a
        non-identifying tombstone at the reserved `.invalid` TLD, which satisfies
        the constraint and can never route anywhere.

        Bookings and orders are untouched: a hard delete would break financial
        history.
        """
        result = await self.session.execute(
            update(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .values(
                status=UserStatus.DELETED,
                deleted_at=now,
                phone=None,
                email=f"deleted+{user_id}@invalid",
                avatar_url=None,
                login=None,
                password_hash=None,
                first_name="",
                last_name="",
            )
            .returning(User)
        )
        await self.session.flush()
        return result.scalars().one_or_none()
