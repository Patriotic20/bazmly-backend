"""Account deletion is a soft delete: identity goes, accounting history stays."""

from datetime import time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.modules.auth.enums import UserStatus
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.services import UserService
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import TableReservationCreate
from app.modules.bookings.services import BookingService
from tests.repositories import factories


async def test_soft_delete_clears_contact_fields_and_revokes_tokens(
    session: AsyncSession,
) -> None:
    user = await factories.make_user(session)
    original_phone = user.phone

    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash="hash-value",
            expires_at=utcnow_naive() + timedelta(days=30),
        )
    )
    await session.flush()

    await UserService(session).delete_account(user.id)

    deleted = await session.get(User, user.id)
    assert deleted is not None
    assert deleted.status == UserStatus.DELETED
    assert deleted.deleted_at is not None
    # The phone is released so the number can register again; the email becomes a
    # non-routable tombstone, because `ck_users_phone_or_email` requires one of the
    # two to survive. See DECISIONS.md.
    assert deleted.phone is None
    assert deleted.email == f"deleted+{user.id}@invalid"
    assert deleted.avatar_url is None
    assert deleted.password_hash is None
    assert original_phone is not None

    tokens = (
        (await session.execute(select(RefreshToken).where(RefreshToken.user_id == user.id)))
        .scalars()
        .all()
    )
    assert tokens, "the row should still exist"
    assert all(token.revoked_at is not None for token in tokens)


async def test_soft_delete_leaves_bookings_intact(session: AsyncSession) -> None:
    """Bookings and orders survive: a hard delete would break the financial
    history the venue and the tax authority both still need."""
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    await factories.make_working_hours(session, venue, time(8, 0), time(23, 0))
    table = await factories.make_table(session, venue, seats=4)
    user = await factories.make_user(session)

    detail = await BookingService(session).create_table_reservation(
        user.id,
        TableReservationCreate(
            venue_id=venue.id,
            table_id=table.id,
            booking_date=utcnow_naive().date() + timedelta(days=7),
            start_time=time(19, 0),
            end_time=time(21, 0),
            guests_count=2,
            contact_name="Test Guest",
            contact_phone="+998901112233",
        ),
    )

    await UserService(session).delete_account(user.id)

    booking = await session.get(Booking, detail.booking.id)
    assert booking is not None
    assert booking.user_id == user.id
    assert booking.total_amount == Decimal("0.00")

    remaining = (
        await session.execute(
            select(func.count()).select_from(Booking).where(Booking.user_id == user.id)
        )
    ).scalar_one()
    assert remaining == 1


async def test_deleted_user_is_invisible_to_normal_reads(session: AsyncSession) -> None:
    from app.modules.auth.repositories import UserRepository

    user = await factories.make_user(session)
    await UserService(session).delete_account(user.id)

    users = UserRepository(session)
    assert await users.get_by_id(user.id) is None
    assert await users.get_by_id_including_deleted(user.id) is not None


async def test_setting_a_name_promotes_pending_profile_to_active(
    session: AsyncSession,
) -> None:
    """The second half of the registration state machine."""
    from app.modules.auth.schemas import UserProfileUpdate

    # `users.language_id` survived the translation collapse: it is the account's UI
    # language preference, which the frontend reads, not content localisation.
    language = await factories.get_language(session)
    user = User(
        first_name="",
        last_name="",
        phone=f"+9989{factories.unique_suffix()[:9]}",
        language_id=language.id,
        role="customer",
        status=UserStatus.PENDING_PROFILE,
        must_change_password=False,
    )
    session.add(user)
    await session.flush()

    updated = await UserService(session).update_profile(
        user.id, UserProfileUpdate(first_name="Ali", last_name="Valiyev")
    )

    assert updated.status == UserStatus.ACTIVE
