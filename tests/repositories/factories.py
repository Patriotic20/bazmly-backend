"""Row builders for the repository tests.

Reference data (staff roles, permissions) is already in the database —
the seed revision put it there — so these only build the per-test rows on top.

Every factory flushes but never commits: the caller's transaction decides.
"""

import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.geo.models import District, Region
from app.modules.menu.models import (
    MenuCategory,
    MenuItem,
    MenuItemBranch,
    MenuItemStatus,
)
from app.modules.services.models import ServiceCatalog
from app.modules.staff.models import (
    Permission,
    StaffRole,
    StaffRolePermission,
    VenueStaff,
)
from app.modules.venue_groups.models import VenueGroup, VenueGroupStatus
from app.modules.venues.enums import VenueTypeSlug
from app.modules.venues.models import (
    Venue,
    VenueStatus,
    VenueTable,
    VenueWorkingHours,
)


def unique_suffix() -> str:
    return uuid.uuid4().hex[:10]


async def get_staff_role(session: AsyncSession, slug: str = "waiter") -> StaffRole:
    result = await session.execute(select(StaffRole).where(StaffRole.slug == slug))
    return result.scalar_one()


async def make_region(session: AsyncSession) -> Region:
    region = Region(name=f"Region {unique_suffix()}", code=unique_suffix()[:6])
    session.add(region)
    await session.flush()
    return region


async def make_district(session: AsyncSession) -> District:
    region = await make_region(session)
    district = District(
        region_id=region.id,
        name=f"District {unique_suffix()}",
        latitude=Decimal("41.311081"),
        longitude=Decimal("69.240562"),
    )
    session.add(district)
    await session.flush()
    return district


async def make_user(session: AsyncSession, role: str = UserRole.CUSTOMER) -> User:
    user = User(
        first_name="Test",
        last_name="User",
        phone=f"+9989{unique_suffix()[:9]}",
        role=role,
        status=UserStatus.ACTIVE,
        must_change_password=False,
    )
    session.add(user)
    await session.flush()
    return user


async def make_venue_group(
    session: AsyncSession,
    owner: User | None = None,
    venue_type: VenueTypeSlug = VenueTypeSlug.RESTORAN,
) -> VenueGroup:
    owner = owner or await make_user(session, role=UserRole.VENUE_OWNER)
    group = VenueGroup(
        owner_id=owner.id,
        primary_venue_type=venue_type,
        name=f"Tarmoq {unique_suffix()}",
        default_currency="UZS",
        status=VenueGroupStatus.ACTIVE,
    )
    session.add(group)
    await session.flush()
    return group


async def make_venue(
    session: AsyncSession,
    *,
    group: VenueGroup | None = None,
    name: str = "Test Venue",
    latitude: float = 41.311081,
    longitude: float = 69.240562,
    status: str = VenueStatus.ACTIVE,
    venue_type: VenueTypeSlug = VenueTypeSlug.RESTORAN,
) -> Venue:
    """A venue at a real Tashkent coordinate, with an active status by default."""
    group = group or await make_venue_group(session)
    district = await make_district(session)

    venue = Venue(
        venue_group_id=group.id,
        owner_id=group.owner_id,
        district_id=district.id,
        venue_type=venue_type,
        street="Amir Temur",
        house_number="1",
        latitude=Decimal(str(latitude)),
        longitude=Decimal(str(longitude)),
        phone=f"+9987{unique_suffix()[:8]}",
        currency="UZS",
        min_advance_booking_days=1,
        late_grace_minutes=40,
        requires_deposit=False,
        rating_avg=Decimal("0.0"),
        reviews_count=0,
        status=status,
        onboarding_step=0,
        name=name,
    )
    session.add(venue)
    await session.flush()
    return venue


async def make_service_catalog_entry(
    session: AsyncSession,
    *,
    applies_to_venue_type: VenueTypeSlug | None = None,
    name: str = "Dasturxon tuzash",
) -> ServiceCatalog:
    """One row of the platform-owned service catalogue.

    Built rather than read from the seed on purpose: every seeded row has a NULL
    `applies_to_venue_type`, so a filter test that leaned on them would pass even
    if the type-specific leg were broken.
    """
    entry = ServiceCatalog(
        slug=f"xizmat-{unique_suffix()}",
        name=name,
        applies_to_venue_type=applies_to_venue_type,
        sort_order=0,
        is_active=True,
    )
    session.add(entry)
    await session.flush()
    return entry


async def make_working_hours(
    session: AsyncSession,
    venue: Venue,
    opens_at: time = time(8, 0),
    closes_at: time = time(20, 0),
) -> None:
    """Seven rows, one per weekday, matching how onboarding writes them."""
    for weekday in range(7):
        session.add(
            VenueWorkingHours(
                venue_id=venue.id,
                weekday=weekday,
                opens_at=opens_at,
                closes_at=closes_at,
                is_closed=False,
            )
        )
    await session.flush()


async def make_table(
    session: AsyncSession, venue: Venue, number: int = 1, seats: int = 4
) -> VenueTable:
    table = VenueTable(venue_id=venue.id, number=number, seats=seats, is_active=True)
    session.add(table)
    await session.flush()
    return table


async def make_staff(
    session: AsyncSession, venue: Venue, group: VenueGroup, role_slug: str = "waiter"
) -> VenueStaff:
    """`role_scope` is denormalized and pinned by a composite FK, so it has to
    match the role's own scope or the insert is rejected."""
    user = await make_user(session, role=UserRole.VENUE_STAFF)
    role = await get_staff_role(session, role_slug)
    staff = VenueStaff(
        venue_group_id=group.id,
        venue_id=venue.id,
        user_id=user.id,
        staff_role_id=role.id,
        role_scope=role.scope,
        is_active=True,
        invited_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(staff)
    await session.flush()
    return staff


async def make_menu_item(
    session: AsyncSession,
    group: VenueGroup,
    *,
    name: str = "Osh",
    base_price: Decimal = Decimal("45000.00"),
) -> MenuItem:
    category = MenuCategory(venue_group_id=group.id, name="Taomlar", sort_order=0, is_active=True)
    session.add(category)
    await session.flush()

    item = MenuItem(
        menu_category_id=category.id,
        name=name,
        base_price=base_price,
        currency="UZS",
        is_available=True,
        sort_order=0,
        has_variants=False,
        status=MenuItemStatus.ACTIVE,
    )
    session.add(item)
    await session.flush()
    return item


async def make_menu_branch(
    session: AsyncSession,
    item: MenuItem,
    venue: Venue,
    price_override: Decimal | None = None,
) -> MenuItemBranch:
    branch = MenuItemBranch(
        menu_item_id=item.id,
        venue_id=venue.id,
        is_available=True,
        price_override=price_override,
    )
    session.add(branch)
    await session.flush()
    return branch


async def grant(session: AsyncSession, role_slug: str, *slugs: str) -> None:
    """Make sure a seeded role carries these permissions.

    `4f2ba1c07d9e` seeds the role/permission matrix, so most of what a test asks
    for is already there. Idempotent rather than additive: the assertion a test
    cares about is "this role can do X", not "this row was inserted by me", and
    `staff_role_permissions` has a composite primary key that would reject the
    duplicate.
    """
    role = (
        await session.execute(select(StaffRole).where(StaffRole.slug == role_slug))
    ).scalar_one()
    for slug in slugs:
        permission = (
            await session.execute(select(Permission).where(Permission.slug == slug))
        ).scalar_one()
        await session.execute(
            pg_insert(StaffRolePermission)
            .values(staff_role_id=role.id, permission_id=permission.id)
            .on_conflict_do_nothing()
        )
    await session.flush()


def business_day() -> date:
    return date(2026, 8, 1)
