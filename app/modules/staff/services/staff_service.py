from collections.abc import Sequence
from datetime import timedelta
from typing import Any

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
    StaffPasswordReset,
    StaffRoleRead,
    VenueStaffListItem,
    VenueStaffRead,
    VenueStaffUpdate,
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
        """Create the employee outright and hand back the login and password once.

        The person is a working account the moment this returns: they sign in
        with these credentials and appear in the staff list straight away. There
        is no accept step — nothing in the app ever offered one, so every
        invitation issued before this stayed a login that did not exist.

        The invitation row is still written, already accepted, as the record of
        who was added when. Returning a live credential is a deliberate exception
        to the rule that no read schema carries a secret: with SMS gone there is
        no channel to deliver it but the owner's own screen. It is returned by
        this call alone — never by a list or a re-read. See DECISIONS.md.
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

        now = utcnow_naive()
        password = generate_password()
        temporary_password: str | None = password
        user = await self.users.get_by_phone(payload.phone)
        if user is None:
            names = payload.full_name.split(" ", 1)
            user = await self.users.create(
                User(
                    first_name=names[0],
                    last_name=names[1] if len(names) > 1 else "",
                    phone=payload.phone,
                    role=UserRole.VENUE_STAFF,
                    status=UserStatus.ACTIVE,
                )
            )
        login = user.login or generate_login()
        if user.password_hash is None:
            await self.users.set_credentials(user.id, login, hash_secret(password), True)
        else:
            # Someone who already signs in with their own password keeps it; the
            # owner must not be able to reset a stranger's account by typing
            # their number. They sign in by phone as before.
            temporary_password = None
            login = user.login or payload.phone

        try:
            invitation = await self.invitations.create(
                StaffInvitation(
                    venue_group_id=group_id,
                    venue_id=payload.venue_id,
                    full_name=payload.full_name,
                    phone=payload.phone,
                    staff_role_id=role.id,
                    temp_password_hash=hash_secret(password),
                    expires_at=now + INVITATION_TTL,
                    accepted_at=now,
                )
            )
            await self.staff.create(
                VenueStaff(
                    venue_group_id=group_id,
                    venue_id=payload.venue_id,
                    user_id=user.id,
                    staff_role_id=role.id,
                    role_scope=role.scope,
                    is_active=True,
                    invited_at=now,
                    activated_at=now,
                )
            )
            await self.session.commit()
        except IntegrityError as error:
            raise translate_integrity_error(error) from error

        return StaffInvitationCreated(
            **StaffInvitationRead.model_validate(invitation).model_dump(),
            login=login,
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

    async def _manageable_in_transaction(self, actor_user_id: int, staff_id: int) -> VenueStaff:
        """The employment row, once the actor is shown to manage *its* staff.

        The route guard only proves `staff.manage` at the branch named in the
        query, not that the row belongs there — without this, any manager could
        edit anyone in any chain by changing the id. A branch row is checked at
        its branch; a chain-wide row (owner, admin) against the chain.
        """
        target = await self.staff.get_by_id(staff_id)
        if target is None:
            raise NotFoundError("Hodim topilmadi")
        if target.venue_id is not None:
            await self.require_permission_in_transaction(
                actor_user_id, target.venue_id, PERM_STAFF_MANAGE
            )
        else:
            await self.require_group_permission_in_transaction(
                actor_user_id, target.venue_group_id, PERM_STAFF_MANAGE
            )
        role = await self.roles.get_by_id(target.staff_role_id)
        # The owner is the chain itself: demoting or switching them off would
        # leave nobody able to undo it.
        if role is not None and role.slug == "owner":
            raise PermissionDeniedError("Muassasa egasini tahrirlab bo'lmaydi")
        return target

    async def _own_staff_account(self, user_id: int) -> User:
        """The user behind an employment, if it is an account opened for the job.

        Someone who joined with their own account keeps their name and password
        to themselves; an owner typing in their staff list must not be able to
        reset a stranger's login.
        """
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Hodim topilmadi")
        if user.role != UserRole.VENUE_STAFF:
            raise ValidationFailedError(
                "Bu hodim o'z akkaunti bilan kiradi — ismi va parolini o'zi o'zgartiradi"
            )
        return user

    async def update(
        self, actor_user_id: int, staff_id: int, payload: VenueStaffUpdate
    ) -> VenueStaffListItem:
        target = await self._manageable_in_transaction(actor_user_id, staff_id)
        changes = payload.model_dump(exclude_unset=True)

        if "first_name" in changes and changes["first_name"] is None:
            raise ValidationFailedError("Ism bo'sh bo'lishi mumkin emas")
        names: dict[str, Any] = {
            key: (changes[key] or "").strip()
            for key in ("first_name", "last_name")
            if key in changes
        }
        if names:
            user = await self._own_staff_account(target.user_id)
            await self.users.update_profile(user.id, names)

        if changes.get("staff_role_id") not in (None, target.staff_role_id):
            role = await self.roles.get_by_id(changes["staff_role_id"])
            if role is None or role.slug == "owner":
                raise NotFoundError("Bunday rol mavjud emas")
            if role.scope == "venue" and target.venue_id is None:
                raise ValidationFailedError(
                    "Filial darajasidagi rol uchun filial ko'rsatilishi kerak"
                )
            await self.staff.set_role(target.id, role.id, role.scope)

        if changes.get("is_active") is not None:
            await self.staff.set_active(target.id, changes["is_active"], utcnow_naive())

        try:
            await self.session.commit()
        except IntegrityError as error:
            raise translate_integrity_error(error) from error

        rows = await self.list_for_group(target.venue_group_id)
        return next(row for row in rows if row.id == target.id)

    async def reset_password(self, actor_user_id: int, staff_id: int) -> StaffPasswordReset:
        """A fresh password for a staff account, returned once.

        The login stays; only the password changes, so the person keeps signing
        in where they did and the old password stops working at once.
        """
        target = await self._manageable_in_transaction(actor_user_id, staff_id)
        user = await self._own_staff_account(target.user_id)
        login = user.login or generate_login()
        password = generate_password()
        await self.users.set_credentials(user.id, login, hash_secret(password), True)
        await self.session.commit()
        return StaffPasswordReset(login=login, temporary_password=password)

    async def set_active(
        self, actor_user_id: int, venue_id: int, staff_id: int, is_active: bool
    ) -> VenueStaffRead:
        await self.require_permission_in_transaction(actor_user_id, venue_id, PERM_STAFF_MANAGE)
        await self._manageable_in_transaction(actor_user_id, staff_id)
        updated = await self.staff.set_active(staff_id, is_active, utcnow_naive())
        if updated is None:
            raise NotFoundError("Hodim topilmadi")
        await self.session.commit()
        return VenueStaffRead.model_validate(updated)

    async def expire_stale_invitations(self) -> Sequence[int]:
        ids = await self.invitations.expire_stale(utcnow_naive())
        await self.session.commit()
        return ids
