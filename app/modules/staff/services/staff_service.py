from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_mode import auth_disabled
from app.core.database.mixins import utcnow_naive
from app.core.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.core.integrity import translate_integrity_error
from app.core.security import generate_login, generate_password, hash_secret, verify_secret
from app.modules.auth.enums import UserRole, UserStatus
from app.modules.auth.models import User
from app.modules.auth.repositories import UserRepository
from app.modules.auth.schemas import UserListItem
from app.modules.staff.enums import StaffRoleScope
from app.modules.staff.models import StaffInvitation, VenueStaff
from app.modules.staff.repositories import (
    PermissionRepository,
    StaffInvitationRepository,
    StaffRoleRepository,
    VenueStaffRepository,
)
from app.modules.staff.schemas import (
    InvitationAccept,
    StaffCountsRead,
    StaffInvitationCreate,
    StaffInvitationCreated,
    StaffInvitationRead,
    StaffRoleRead,
    VenueStaffListItem,
    VenueStaffRead,
)

INVITATION_TTL = timedelta(hours=72)

PERM_STAFF_MANAGE = "staff.manage"


class StaffService:
    """Employment and the permission guard every owner-side write goes through."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.staff = VenueStaffRepository(session)
        self.roles = StaffRoleRepository(session)
        self.permissions = PermissionRepository(session)
        self.invitations = StaffInvitationRepository(session)
        self.users = UserRepository(session)

    async def require_permission_in_transaction(
        self, user_id: int, venue_id: int, permission_slug: str
    ) -> None:
        """The guard. Answered by one join in the database, never in Python.

        A group-scoped row (`venue_id IS NULL`) belongs to an owner or admin and
        satisfies a venue-scoped check at any branch in their chain, which is why
        the repository predicate is an OR rather than an equality.

        Failure raises. It is never a silent no-op, because a write that quietly
        does nothing is indistinguishable from one that worked.
        """
        # Services check permissions independently of the route guard — twelve call
        # sites do — so the kill switch has to be honoured here too, or turning auth
        # off would open the reads and leave every staff write at 403.
        if auth_disabled():
            return
        allowed = await self.staff.has_permission(user_id, venue_id, permission_slug)
        if not allowed:
            raise PermissionDeniedError(
                "Bu yerda bu amalni bajarishga ruxsatingiz yo'q",
                details={"permission": permission_slug, "venue_id": venue_id},
            )

    async def require_group_permission_in_transaction(
        self, user_id: int, venue_group_id: int, permission_slug: str
    ) -> None:
        """The chain-scoped guard, for routes that create a branch.

        There is no `venue_id` to check against yet, so the question becomes
        whether the caller holds the permission anywhere in the chain.
        """
        if auth_disabled():
            return
        allowed = await self.staff.has_group_permission(user_id, venue_group_id, permission_slug)
        if not allowed:
            raise PermissionDeniedError(
                "Bu tarmoqda bu amalni bajarishga ruxsatingiz yo'q",
                details={"permission": permission_slug, "group_id": venue_group_id},
            )

    async def employment_for_in_transaction(self, user_id: int, venue_id: int) -> VenueStaff:
        """The `venue_staff` row that order writes are attributed to.

        Falls back to the group-level row so an owner acting at a branch is still
        recorded as the actor rather than failing for lack of a branch row.
        """
        row = await self.staff.get_for_user_and_venue(user_id, venue_id)
        if row is not None:
            return row
        for candidate in await self.staff.list_for_user(user_id):
            if candidate.venue_id is None:
                return candidate
        raise PermissionDeniedError("Siz bu muassasada ishlamaysiz")

    async def group_ids_for(self, user_id: int) -> set[int]:
        """Every chain the person actively works in — the membership test behind
        `VerifiedGroupId`."""
        return {row.venue_group_id for row in await self.staff.list_for_user(user_id)}

    async def list_for_group(
        self,
        group_id: int,
        venue_id: int | None = None,
        role_id: int | None = None,
        is_active: bool | None = None,
    ) -> Sequence[VenueStaffListItem]:
        rows = await self.staff.list_for_group(group_id, venue_id, role_id, is_active)
        roles = {row.id: row.name for row in await self.roles.list_active()}
        users = {
            user.id: user for user in await self.users.list_by_ids([row.user_id for row in rows])
        }
        return [
            VenueStaffListItem(
                id=row.id,
                venue_id=row.venue_id,
                staff_role_id=row.staff_role_id,
                role_name=roles.get(row.staff_role_id, ""),
                is_active=row.is_active,
                user=UserListItem.model_validate(users[row.user_id]),
            )
            for row in rows
            if row.user_id in users
        ]

    async def counts(self, group_id: int) -> StaffCountsRead:
        counts = await self.staff.count_by_active_for_group(group_id)
        return StaffCountsRead(total=counts.total, active=counts.active, inactive=counts.inactive)

    async def list_roles(self, scope: str | None = None) -> Sequence[StaffRoleRead]:
        rows = await self.roles.list_active(scope)
        return [
            StaffRoleRead(
                id=row.id,
                slug=row.slug,
                scope=StaffRoleScope(row.scope),
                name=row.name,
                sort_order=row.sort_order,
            )
            for row in rows
        ]

    async def invite(
        self,
        actor_user_id: int,
        group_id: int,
        payload: StaffInvitationCreate,
    ) -> StaffInvitationCreated:
        """Issue a login and a temporary password, store the hash, return both once.

        Returning a live credential is a deliberate exception to the rule that no
        read schema carries a secret. With SMS gone there is no channel left to
        deliver it, and an invitation nobody can redeem is worse than one the owner
        reads off their own screen and hands over. It is returned by this call
        alone — never by a list or a re-read — it expires, and
        `must_change_password` forces rotation on first login. See DECISIONS.md.
        """
        guard_venue = payload.venue_id
        if guard_venue is None:
            branches = await self.staff.list_for_group(group_id)
            guard_venue = next((row.venue_id for row in branches if row.venue_id is not None), None)
        if guard_venue is not None:
            await self.require_permission_in_transaction(
                actor_user_id, guard_venue, PERM_STAFF_MANAGE
            )

        role = await self.roles.get_by_id(payload.staff_role_id)
        if role is None:
            raise NotFoundError("Bunday rol mavjud emas")
        if role.scope == "venue" and payload.venue_id is None:
            raise ValidationFailedError("Filial darajasidagi rol uchun filial ko'rsatilishi kerak")

        temporary_password = generate_password()
        suggested_login = generate_login()
        invitation = await self.invitations.create(
            StaffInvitation(
                venue_group_id=group_id,
                venue_id=payload.venue_id,
                full_name=payload.full_name,
                phone=payload.phone,
                staff_role_id=payload.staff_role_id,
                temp_password_hash=hash_secret(temporary_password),
                expires_at=utcnow_naive() + INVITATION_TTL,
            )
        )
        await self.session.commit()
        # `login` is advisory — the invitation row has no column for it, so
        # `accept_invitation` uses whatever login the person supplies. See
        # DECISIONS.md.
        return StaffInvitationCreated(
            **StaffInvitationRead.model_validate(invitation).model_dump(),
            login=suggested_login,
            temporary_password=temporary_password,
        )

    async def accept_invitation(self, payload: InvitationAccept, phone: str) -> VenueStaffRead:
        """Redeem an invitation into a user and an employment row.

        `must_change_password` is cleared here because the person is choosing their
        own password in the same step — a forwarded SMS is therefore not a
        permanent key to the till.
        """
        now = utcnow_naive()
        invitation = await self.invitations.get_active_by_phone(phone, now)
        if invitation is None:
            raise NotFoundError("Bu raqam uchun faol taklifnoma yo'q")
        if not verify_secret(payload.temporary_password, invitation.temp_password_hash):
            raise PermissionDeniedError("Vaqtinchalik parol noto'g'ri")

        user = await self.users.get_by_phone(phone)
        if user is None:
            names = invitation.full_name.split(" ", 1)
            user = await self.users.create(
                User(
                    first_name=names[0],
                    last_name=names[1] if len(names) > 1 else "",
                    phone=phone,
                    role=UserRole.VENUE_STAFF,
                    status=UserStatus.ACTIVE,
                    must_change_password=False,
                )
            )

        await self.users.set_credentials(
            user.id, payload.login, hash_secret(payload.new_password), False
        )

        role = await self.roles.get_by_id(invitation.staff_role_id)
        if role is None:
            raise NotFoundError("Bu rol endi mavjud emas")

        try:
            employment = await self.staff.create(
                VenueStaff(
                    venue_group_id=invitation.venue_group_id,
                    venue_id=invitation.venue_id,
                    user_id=user.id,
                    staff_role_id=role.id,
                    role_scope=role.scope,
                    is_active=True,
                    invited_at=invitation.created_at,
                    activated_at=now,
                )
            )
            await self.invitations.accept(invitation.id, now)
            await self.session.commit()
        except IntegrityError as error:
            raise translate_integrity_error(error) from error

        return VenueStaffRead.model_validate(employment)

    async def set_active(
        self, actor_user_id: int, venue_id: int, staff_id: int, is_active: bool
    ) -> VenueStaffRead:
        await self.require_permission_in_transaction(actor_user_id, venue_id, PERM_STAFF_MANAGE)
        updated = await self.staff.set_active(staff_id, is_active, utcnow_naive())
        if updated is None:
            raise NotFoundError("Hodim topilmadi")
        await self.session.commit()
        return VenueStaffRead.model_validate(updated)

    async def expire_stale_invitations(self) -> Sequence[int]:
        ids = await self.invitations.expire_stale(utcnow_naive())
        await self.session.commit()
        return ids
