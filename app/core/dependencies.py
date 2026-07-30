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

from fastapi import Depends, Header, Path, Query, Request, params
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database.db_helper import db_helper
from app.core.exceptions import PermissionDeniedError, ValidationFailedError
from app.core.security import TokenError, decode_access_token
from app.modules.auth.enums import UserStatus
from app.modules.auth.schemas import UserRead
from app.modules.auth.services import UserService
from app.modules.localization.repositories import DEFAULT_LANGUAGE_CODE
from app.modules.localization.services import LanguageService
from app.modules.staff.services import StaffService

BEARER_PREFIX = "bearer "

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


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith(BEARER_PREFIX):
        return None
    return authorization[len(BEARER_PREFIX) :].strip() or None


async def get_current_user(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> UserRead:
    """Decode the access token and load the user.

    A soft-deleted or non-active account is rejected here rather than deeper in,
    so no service ever has to ask whether its caller still exists.
    """
    token = _bearer_token(authorization)
    if token is None:
        raise PermissionDeniedError("Authentication required")

    try:
        user_id = decode_access_token(token, settings.security.secret_key)
    except TokenError as error:
        raise PermissionDeniedError("Access token is not valid") from error

    # `get_profile` already excludes soft-deleted rows.
    user = await UserService(session).get_profile(user_id)
    if user.status != UserStatus.ACTIVE:
        raise PermissionDeniedError(
            "This account is not active",
            details={"status": user.status},
        )
    return user


CurrentUser = Annotated[UserRead, Depends(get_current_user)]


async def get_current_user_pending_ok(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> UserRead:
    """Like `get_current_user`, but accepts `pending_profile`.

    Exactly one endpoint needs this — `complete-profile`, which is what promotes a
    verified phone into a usable account. Requiring `active` there would be a
    deadlock: you could not set your name until you were active, and you could not
    become active without setting your name.

    Blocked and deleted accounts are still refused.
    """
    token = _bearer_token(authorization)
    if token is None:
        raise PermissionDeniedError("Authentication required")

    try:
        user_id = decode_access_token(token, settings.security.secret_key)
    except TokenError as error:
        raise PermissionDeniedError("Access token is not valid") from error

    user = await UserService(session).get_profile(user_id)
    if user.status not in (UserStatus.ACTIVE, UserStatus.PENDING_PROFILE):
        raise PermissionDeniedError("This account is not active", details={"status": user.status})
    return user


PendingUser = Annotated[UserRead, Depends(get_current_user_pending_ok)]


async def get_current_user_optional(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> UserRead | None:
    """For endpoints that personalise but do not require auth.

    A bad token is treated as no token: venue search must not start returning 403
    because someone's session quietly expired.
    """
    if _bearer_token(authorization) is None:
        return None
    try:
        return await get_current_user(session, authorization)
    except PermissionDeniedError:
        return None


OptionalUser = Annotated[UserRead | None, Depends(get_current_user_optional)]


async def get_language_id(
    session: SessionDep,
    user: OptionalUser,
    accept_language: Annotated[str | None, Header()] = None,
) -> int:
    """`Accept-Language` → the signed-in user's language → uz.

    The header wins over the stored preference because a person switching their
    phone's language expects the app to follow immediately, without a profile edit.
    """
    languages = LanguageService(session)

    if accept_language:
        # "uz-UZ,uz;q=0.9,ru;q=0.8" -> try each tag in the order offered.
        for part in accept_language.split(","):
            tag = part.split(";")[0].strip().split("-")[0].lower()
            if not tag:
                continue
            language = await languages.get_by_code(tag)
            if language is not None:
                return language.id

    if user is not None:
        return user.language_id

    fallback = await languages.get_by_code(DEFAULT_LANGUAGE_CODE)
    if fallback is None:
        raise ValidationFailedError("No languages are configured")
    return fallback.id


LanguageId = Annotated[int, Depends(get_language_id)]


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
        raise ValidationFailedError("lat and lng must be supplied together")
    return ClientLocation(latitude=lat, longitude=lng)


ClientLocationDep = Annotated[ClientLocation | None, Depends(get_client_location)]


def require_permission(slug: str) -> params.Depends:
    """Dependency factory guarding every staff-facing write.

    `venue_id` is read from the path when the route is nested under a branch, and
    from the query otherwise. Group-scoped roles (owner, admin) satisfy a
    venue-scoped check at any branch in their chain — that rule lives in
    `VenueStaffRepository.has_permission`, one join in the database.

    Failure raises rather than returning False, so a caller cannot forget to check
    the result and let an unauthorised write through.
    """

    async def dependency(
        request: Request,
        session: SessionDep,
        user: CurrentUser,
        venue_id_query: Annotated[int | None, Query(alias="venue_id")] = None,
    ) -> int:
        raw = request.path_params.get("venue_id", venue_id_query)
        if raw is None:
            raise ValidationFailedError(
                "venue_id is required for this operation",
                details={"permission": slug},
            )
        venue_id = int(raw)
        await StaffService(session).require_permission_in_transaction(user.id, venue_id, slug)
        return venue_id

    guard: params.Depends = Depends(dependency)
    return guard


def venue_id_path(venue_id: Annotated[int, Path(ge=1)]) -> int:
    return venue_id
