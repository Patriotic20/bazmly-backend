from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.core.integrity import translate_integrity_error
from app.core.security import generate_password, hash_secret, verify_secret
from app.core.transports import get_sms_sender
from app.modules.auth.enums import UserRole, UserStatus
from app.modules.auth.models import User
from app.modules.auth.repositories import UserRepository
from app.modules.auth.schemas import UserListItem
from app.modules.localization.repositories import DEFAULT_LANGUAGE_CODE, LanguageRepository
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
        self.languages = LanguageRepository(session)

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
        allowed = await self.staff.has_permission(user_id, venue_id, permission_slug)
        if not allowed:
            raise PermissionDeniedError(
                "You do not have permission to do that here",
                details={"permission": permission_slug, "venue_id": venue_id},
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
        raise PermissionDeniedError("You are not staff at this venue")

    async def list_for_group(
        self,
        group_id: int,
        language_id: int,
        venue_id: int | None = None,
        role_id: int | None = None,
        is_active: bool | None = None,
    ) -> Sequence[VenueStaffListItem]:
        rows = await self.staff.list_for_group(group_id, venue_id, role_id, is_active)
        roles = {row.role.id: row.name for row in await self.roles.list_active(language_id)}
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

    async def list_roles(
        self, language_id: int, scope: str | None = None
    ) -> Sequence[StaffRoleRead]:
        rows = await self.roles.list_active(language_id, scope)
        return [
            StaffRoleRead(
                id=row.role.id,
                slug=row.role.slug,
                scope=StaffRoleScope(row.role.scope),
                name=row.name,
                sort_order=row.role.sort_order,
            )
            for row in rows
        ]

    async def invite(
        self,
        actor_user_id: int,
        group_id: int,
        payload: StaffInvitationCreate,
    ) -> StaffInvitationRead:
        """Issue a login and a temporary password, send them once, store hashes.

        The plaintext password exists in memory only long enough to reach the SMS
        transport. It is never returned, never persisted and never logged — the
        transport logs that a message was sent, not what it said.
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
            raise NotFoundError("That role does not exist")
        if role.scope == "venue" and payload.venue_id is None:
            raise ValidationFailedError("A venue-scoped role needs a branch")

        temporary_password = generate_password()
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

        await get_sms_sender().send(
            payload.phone,
            f"Bazmly: vaqtinchalik parol {temporary_password}. 72 soat amal qiladi.",
        )
        return StaffInvitationRead.model_validate(invitation)

    async def accept_invitation(self, payload: InvitationAccept, phone: str) -> VenueStaffRead:
        """Redeem an invitation into a user and an employment row.

        `must_change_password` is cleared here because the person is choosing their
        own password in the same step — a forwarded SMS is therefore not a
        permanent key to the till.
        """
        now = utcnow_naive()
        invitation = await self.invitations.get_active_by_phone(phone, now)
        if invitation is None:
            raise NotFoundError("No active invitation for that number")
        if not verify_secret(payload.temporary_password, invitation.temp_password_hash):
            raise PermissionDeniedError("The temporary password is incorrect")

        user = await self.users.get_by_phone(phone)
        if user is None:
            language = await self.languages.get_by_code(DEFAULT_LANGUAGE_CODE)
            if language is None:
                raise ValidationFailedError("No default language is configured")
            names = invitation.full_name.split(" ", 1)
            user = await self.users.create(
                User(
                    first_name=names[0],
                    last_name=names[1] if len(names) > 1 else "",
                    phone=phone,
                    language_id=language.id,
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
            raise NotFoundError("That role no longer exists")

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
            raise NotFoundError("Staff member not found")
        await self.session.commit()
        return VenueStaffRead.model_validate(updated)

    async def expire_stale_invitations(self) -> Sequence[int]:
        ids = await self.invitations.expire_stale(utcnow_naive())
        await self.session.commit()
        return ids
