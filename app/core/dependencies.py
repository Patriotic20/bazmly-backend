"""Request-scoped dependencies.

Everything an endpoint needs that is not its own service call lives here, so the
endpoints themselves stay three to six lines: resolve, call one service method,
return.

Nothing here raises `HTTPException`. Failures are `DomainError` subclasses and
`app/core/handlers.py` decides the status code — which is what keeps the HTTP
vocabulary out of the domain and lets the same guard be reused off a request.
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Path, Query, Request, params
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_mode import AuthConfigurationError, auth_disabled, dev_user_id
from app.core.config import settings
from app.core.database.db_helper import db_helper
from app.core.exceptions import (
    AuthenticationRequiredError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.core.security import TokenError, decode_access_token
from app.modules.auth.enums import UserRole, UserStatus
from app.modules.auth.schemas import UserRead
from app.modules.auth.services import UserService
from app.modules.staff.services import StaffService

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


async def get_session() -> AsyncGenerator[AsyncSession]:
    """The only place a session enters a request.

    Every service is constructed from this one session, so a request is one unit
    of work and a service that commits mid-request commits everything before it.
    """
    async for session in db_helper.session_getter():
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Kirish tokeni: `Authorization: Bearer <token>`",
)

BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]
"""The access token, or `None` when absent or not a bearer credential.

`auto_error=False` is load-bearing twice over. It keeps `get_current_user_optional`
able to return `None` instead of failing, and it keeps every rejection a
`DomainError` raised by us — `auto_error=True` would raise `HTTPException` from
inside the security scheme, which is exactly the HTTP vocabulary this module
keeps out of the domain.

FastAPI also returns `None` when the scheme is not `bearer`, which is the same
rule the hand-rolled prefix check enforced.
"""


async def get_current_user(
    session: SessionDep,
    credentials: BearerCredentials = None,
) -> UserRead:
    """Decode the access token and load the user.

    A soft-deleted or non-active account is rejected here rather than deeper in,
    so no service ever has to ask whether its caller still exists.

    A missing or unreadable token is a 401 and a blocked account is a 403: the
    first is fixed by signing in again and the second is not.
    """
    if auth_disabled():
        return await _dev_user(session)

    token = credentials.credentials if credentials else None
    if token is None:
        raise AuthenticationRequiredError()

    try:
        user_id = decode_access_token(token, settings.security.secret_key)
    except TokenError as error:
        raise AuthenticationRequiredError("Kirish tokeni yaroqsiz") from error

    # `get_profile` already excludes soft-deleted rows.
    user = await UserService(session).get_profile(user_id)
    if user.status != UserStatus.ACTIVE:
        raise PermissionDeniedError(
            "Bu akkaunt faol emas",
            details={"status": user.status},
        )
    return user


async def _dev_user(session: AsyncSession) -> UserRead:
    """Who every request is while `AUTH_MODE=disabled`.

    A real row, so `user.id` is a usable foreign key and ownership checks run their
    real code path. A missing row is reported as what it is — a misconfiguration —
    rather than as the 404 `get_profile` would otherwise raise.
    """
    user_id = dev_user_id()
    try:
        return await UserService(session).get_profile(user_id)
    except NotFoundError as error:
        raise AuthConfigurationError(
            f"SECURITY__DEV_USER_ID={user_id} does not exist in `users`."
        ) from error


CurrentUser = Annotated[UserRead, Depends(get_current_user)]


async def get_current_user_pending_ok(
    session: SessionDep,
    credentials: BearerCredentials = None,
) -> UserRead:
    """Like `get_current_user`, but accepts `pending_profile`.

    Exactly one endpoint needs this — `complete-profile`, which is what promotes a
    verified phone into a usable account. Requiring `active` there would be a
    deadlock: you could not set your name until you were active, and you could not
    become active without setting your name.

    Blocked and deleted accounts are still refused.
    """
    if auth_disabled():
        return await _dev_user(session)

    token = credentials.credentials if credentials else None
    if token is None:
        raise AuthenticationRequiredError()

    try:
        user_id = decode_access_token(token, settings.security.secret_key)
    except TokenError as error:
        raise AuthenticationRequiredError("Kirish tokeni yaroqsiz") from error

    user = await UserService(session).get_profile(user_id)
    if user.status not in (UserStatus.ACTIVE, UserStatus.PENDING_PROFILE):
        raise PermissionDeniedError("Bu akkaunt faol emas", details={"status": user.status})
    return user


PendingUser = Annotated[UserRead, Depends(get_current_user_pending_ok)]


async def get_current_user_optional(
    session: SessionDep,
    credentials: BearerCredentials = None,
) -> UserRead | None:
    """For endpoints that personalise but do not require auth.

    A bad token is treated as no token: venue search must not start returning 401
    because someone's session quietly expired.
    """
    if auth_disabled():
        return await _dev_user(session)
    if credentials is None:
        return None
    try:
        return await get_current_user(session, credentials)
    except AuthenticationRequiredError, PermissionDeniedError:
        return None


OptionalUser = Annotated[UserRead | None, Depends(get_current_user_optional)]


@dataclass(frozen=True, slots=True)
class Pagination:
    limit: int
    offset: int


def get_pagination(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


PaginationDep = Annotated[Pagination, Depends(get_pagination)]


@dataclass(frozen=True, slots=True)
class ClientLocation:
    latitude: float
    longitude: float


def get_client_location(
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
) -> ClientLocation | None:
    """Both or neither.

    One coordinate alone is not a partial answer, it is a bug in the caller —
    silently ignoring it would return results sorted by rating while the app shows
    a distance sort.
    """
    if lat is None and lng is None:
        return None
    if lat is None or lng is None:
        raise ValidationFailedError("`lat` va `lng` birgalikda yuborilishi kerak")
    return ClientLocation(latitude=lat, longitude=lng)


ClientLocationDep = Annotated[ClientLocation | None, Depends(get_client_location)]


async def get_verified_group_id(
    session: SessionDep,
    user: CurrentUser,
    group_id: Annotated[int, Query(ge=1)],
) -> int:
    """A required `group_id` that must name a chain the caller works in.

    For the partner reads that have no permission guard of their own. Without
    this, any signed-in user could read another chain's staff list by picking
    its id off a URL — the query param alone is a claim, not authority.
    """
    if auth_disabled():
        return group_id
    if group_id not in await StaffService(session).group_ids_for(user.id):
        raise PermissionDeniedError("Siz bu tarmoqda ishlamaysiz")
    return group_id


VerifiedGroupId = Annotated[int, Depends(get_verified_group_id)]


class PermissionRequired:
    """Guards a staff-facing write, and resolves the caller while it is there.

    `venue_id` is read from the path when the route is nested under a branch, and
    from the query otherwise. Group-scoped roles (owner, admin) satisfy a
    venue-scoped check at any branch in their chain — that rule lives in
    `VenueStaffRepository.has_permission`, one join in the database.

    Failure raises rather than returning False, so a caller cannot forget to check
    the result and let an unauthorised write through. It raises a `DomainError`,
    never `HTTPException`: `app/core/handlers.py` owns the status code.

    Returning the `UserRead` is what lets a route declare one parameter instead of
    two. Before this, a write took both `user: CurrentUser` and the guard, which
    resolved the same user a second time and let the two drift apart in principle.

    A class rather than a closure so the slug is readable from the outside —
    `tests/api/test_contract.py` walks the dependant tree and asserts on
    `.slug`, which a closure could not expose.
    """

    def __init__(self, slug: str, *, venue_in_body: bool = False) -> None:
        self.slug = slug
        self.venue_in_body = venue_in_body

    async def __call__(
        self,
        request: Request,
        session: SessionDep,
        user: CurrentUser,
        venue_id_query: Annotated[int | None, Query(alias="venue_id")] = None,
    ) -> UserRead:
        if auth_disabled():
            return user
        raw = request.path_params.get("venue_id", venue_id_query)
        if self.venue_in_body:
            raw = await self._reconcile_with_body(request, raw)
        if raw is None:
            raise ValidationFailedError(
                "Bu amal uchun `venue_id` talab qilinadi",
                details={"permission": self.slug},
            )
        await StaffService(session).require_permission_in_transaction(user.id, int(raw), self.slug)
        return user

    async def _reconcile_with_body(
        self, request: Request, raw: int | str | None
    ) -> int | str | None:
        """For the routes whose handler acts on the body's `venue_id`.

        Checking any other branch would authorise one venue and act on another,
        so a query value that disagrees with the body is refused rather than
        preferred. The body is already buffered by the time dependencies run;
        reading it again costs nothing.
        """
        try:
            body = await request.json()
        except ValueError:
            return raw
        from_body = body.get("venue_id") if isinstance(body, dict) else None
        if not isinstance(from_body, int | str):
            return raw
        if raw is not None and int(raw) != int(from_body):
            raise ValidationFailedError(
                "So'rovdagi `venue_id` qiymatlari bir-biriga mos emas",
                details={"permission": self.slug},
            )
        return from_body


class GroupPermissionRequired:
    """The same guard, scoped to a chain rather than a branch.

    `PermissionRequired` cannot guard a route that *creates* a branch: it needs a
    `venue_id`, and the branch being created does not have one yet. This resolves
    a `group_id` instead and asks whether the caller holds the slug anywhere in
    that chain — a group-scoped row, or any branch of it.

    Deliberately a second class rather than a `scope=` argument on the first: a
    route picks one scope or the other, and a guard that silently changes meaning
    depending on which query param arrived is the kind that gets misread.
    """

    def __init__(self, slug: str) -> None:
        self.slug = slug

    async def __call__(
        self,
        request: Request,
        session: SessionDep,
        user: CurrentUser,
        group_id_query: Annotated[int | None, Query(alias="group_id")] = None,
    ) -> UserRead:
        if auth_disabled():
            return user
        raw = request.path_params.get("group_id", group_id_query)
        if raw is None:
            raise ValidationFailedError(
                "Bu amal uchun `group_id` talab qilinadi",
                details={"permission": self.slug},
            )
        await StaffService(session).require_group_permission_in_transaction(
            user.id, int(raw), self.slug
        )
        return user


def require_permission(slug: str, *, venue_in_body: bool = False) -> params.Depends:
    """`Depends` around `PermissionRequired`, usable two ways.

    In a signature it hands back the caller:

        user: Annotated[UserRead, require_permission("branch.manage")]

    In `dependencies=[...]` it just guards, for the routes that never need the
    user. Both resolve the same object, so there is one guard, not two shapes.

    `venue_in_body=True` is for a route whose payload names the branch it acts
    on; the guard then checks that branch instead of demanding a query copy.
    """
    guard: params.Depends = Depends(PermissionRequired(slug, venue_in_body=venue_in_body))
    return guard


def require_group_permission(slug: str) -> params.Depends:
    """`Depends` around `GroupPermissionRequired`. See `require_permission`."""
    guard: params.Depends = Depends(GroupPermissionRequired(slug))
    return guard


class PlatformRoleRequired:
    """Guards a platform-wide write on the caller's own `users.role`.

    A different axis from `PermissionRequired`: that one asks what the caller may
    do inside one venue group, which is the wrong question for national reference
    data. A group owner holds `admin` *within their chain* and must not thereby be
    able to rename a viloyat.

    Reads nothing from the database — the role is already on the resolved
    `UserRead`, so this is one comparison and no query.

    A class rather than a closure so `.roles` stays readable from outside, the way
    `tests/api/test_contract.py` reads `.slug` off the staff guards.
    """

    def __init__(self, *roles: UserRole) -> None:
        self.roles = frozenset(roles)

    async def __call__(self, user: CurrentUser) -> UserRead:
        if auth_disabled():
            return user
        if user.role not in self.roles:
            raise PermissionDeniedError(
                "Bu amal uchun ruxsat yo'q",
                details={"required_roles": sorted(role.value for role in self.roles)},
            )
        return user


def require_platform_role(*roles: UserRole) -> params.Depends:
    """`Depends` around `PlatformRoleRequired`. See `require_permission`."""
    guard: params.Depends = Depends(PlatformRoleRequired(*roles))
    return guard


AdminUser = Annotated[UserRead, require_platform_role(UserRole.ADMIN, UserRole.MODERATOR)]


def venue_id_path(venue_id: Annotated[int, Path(ge=1)]) -> int:
    return venue_id
