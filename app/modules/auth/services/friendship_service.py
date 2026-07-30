from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationFailedError
from app.modules.auth.enums import FriendshipStatus
from app.modules.auth.models import Friendship
from app.modules.auth.repositories import FriendshipRepository, UserRepository
from app.modules.auth.schemas import FriendshipRead, FriendshipRespond, UserListItem


class FriendshipService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.friendships = FriendshipRepository(session)
        self.users = UserRepository(session)

    async def request(self, requester_id: int, addressee_id: int) -> FriendshipRead:
        if requester_id == addressee_id:
            raise ValidationFailedError("O'zingizni qo'sha olmaysiz")

        addressee = await self.users.get_by_id(addressee_id)
        if addressee is None:
            raise NotFoundError("Bu foydalanuvchi topilmadi")

        # Either direction counts: the constraint is ordered, the relationship is not.
        existing = await self.friendships.get_between(requester_id, addressee_id)
        if existing is not None:
            return FriendshipRead.model_validate(existing)

        friendship = await self.friendships.create(
            Friendship(
                requester_id=requester_id,
                addressee_id=addressee_id,
                status=FriendshipStatus.PENDING,
            )
        )
        await self.session.commit()
        return FriendshipRead.model_validate(friendship)

    async def respond(
        self, user_id: int, friendship_id: int, payload: FriendshipRespond
    ) -> FriendshipRead:
        friendship = await self.friendships.get_by_id(friendship_id)
        if friendship is None:
            raise NotFoundError("Do'stlik so'rovi topilmadi")
        if friendship.addressee_id != user_id:
            raise PermissionDeniedError("Bu so'rovga faqat qabul qiluvchi javob bera oladi")

        status = FriendshipStatus.ACCEPTED if payload.accept else FriendshipStatus.BLOCKED
        updated = await self.friendships.update_status(friendship_id, status)
        if updated is None:
            raise NotFoundError("Do'stlik so'rovi topilmadi")
        await self.session.commit()
        return FriendshipRead.model_validate(updated)

    async def list_friends(self, user_id: int) -> Sequence[UserListItem]:
        friends = await self.friendships.list_accepted(user_id)
        return [UserListItem.model_validate(friend) for friend in friends]

    async def list_incoming(self, user_id: int) -> Sequence[FriendshipRead]:
        pending = await self.friendships.list_pending_incoming(user_id)
        return [FriendshipRead.model_validate(row) for row in pending]
