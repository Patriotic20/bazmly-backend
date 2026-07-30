from collections.abc import Sequence

from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import Friendship, FriendshipStatus, User


class FriendshipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, friendship_id: int) -> Friendship | None:
        result = await self.session.execute(
            select(Friendship).where(Friendship.id == friendship_id)
        )
        return result.scalar_one_or_none()

    async def get_between(self, user_a: int, user_b: int) -> Friendship | None:
        """Matches either direction — the unique constraint is ordered, the
        relationship is not."""
        result = await self.session.execute(
            select(Friendship).where(
                or_(
                    and_(Friendship.requester_id == user_a, Friendship.addressee_id == user_b),
                    and_(Friendship.requester_id == user_b, Friendship.addressee_id == user_a),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_accepted(self, user_id: int) -> Sequence[User]:
        """The other party of every accepted friendship, in either direction."""
        other_id = case(
            (Friendship.requester_id == user_id, Friendship.addressee_id),
            else_=Friendship.requester_id,
        )
        result = await self.session.execute(
            select(User)
            .join(Friendship, User.id == other_id)
            .where(
                Friendship.status == FriendshipStatus.ACCEPTED,
                or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id),
                User.deleted_at.is_(None),
            )
            .order_by(User.first_name, User.last_name)
        )
        return result.scalars().all()

    async def list_pending_incoming(self, user_id: int) -> Sequence[Friendship]:
        result = await self.session.execute(
            select(Friendship)
            .where(
                Friendship.addressee_id == user_id,
                Friendship.status == FriendshipStatus.PENDING,
            )
            .order_by(Friendship.created_at.desc())
        )
        return result.scalars().all()

    async def create(self, friendship: Friendship) -> Friendship:
        self.session.add(friendship)
        await self.session.flush()
        return friendship

    async def update_status(self, friendship_id: int, status: str) -> Friendship | None:
        result = await self.session.execute(
            update(Friendship)
            .where(Friendship.id == friendship_id)
            .values(status=status)
            .returning(Friendship)
        )
        await self.session.flush()
        return result.scalars().one_or_none()
