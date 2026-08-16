"""Demo data for a local database.

Reference data — languages, staff roles, permissions, the service catalogue,
amenities, and every Uzbek region and district — is seeded by migrations. This
script writes the *demo* layer on top of it: people, chains, branches, zones,
tables, menus, services, bookings, orders and reviews, so that a freshly
migrated database has something to look at in Swagger and in the client.

It is deliberately not a migration. None of these rows belong in staging or
production, and a migration cannot be re-run after every schema change during
development, which is exactly what demo data needs.

    uv run python -m scripts.seed_demo

Every run truncates the demo-owned tables first, so it is idempotent and safe to
repeat. `regions` and `districts` are never touched — those come from the seed
revision. The script refuses to run unless `APP_CONFIG__ENV=local`.
"""

import asyncio
import sys
from collections.abc import Sequence
from datetime import date, time, timedelta
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import AppEnv, settings
from app.core.database.mixins import utcnow_naive
from app.core.security import hash_secret
from app.modules.auth.models import User, UserRole, UserStatus, UserTheme
from app.modules.bookings.models import (
    Booking,
    BookingKind,
    BookingPriceLine,
    BookingService,
    BookingStatus,
    BookingStatusHistory,
    PriceLineType,
)
from app.modules.catalog.models import Amenity
from app.modules.engagement.models import Favorite
from app.modules.geo.models import District, Region
from app.modules.localization.models import Language
from app.modules.menu.models import (
    MenuCategory,
    MenuItem,
    MenuItemBranch,
    MenuItemStatus,
    MenuItemVariant,
)
from app.modules.orders.models import Order, OrderItem, OrderItemStatus, OrderKind, OrderStatus
from app.modules.reviews.models import Review, ReviewStatus
from app.modules.services.models import (
    ServiceCatalog,
    ServicePriceUnit,
    VenueService,
    VenueServiceItem,
)
from app.modules.staff.models import StaffRole, VenueStaff
from app.modules.venue_groups.models import VenueGroup, VenueGroupStatus
from app.modules.venues.enums import VenueTypeSlug
from app.modules.venues.models import (
    Venue,
    VenueAmenity,
    VenueGuestTier,
    VenuePhoto,
    VenueStatus,
    VenueTable,
    VenueWorkingHours,
    VenueZone,
)

# Same list as `tests/conftest.py`, minus `districts` and `regions`: those are
# reference data now and the seed revision owns them.
DEMO_TABLES = (
    "bookings",
    "orders",
    "menu_categories",
    "venue_tables",
    "venue_zones",
    "venues",
    "venue_groups",
    "users",
)

# One password for every demo account, so the accounts are actually usable.
DEMO_PASSWORD = "demo1234"

PHOTO_BASE = "https://picsum.photos/seed"


def _phone(index: int) -> str:
    return f"+9989000{index:05d}"


async def _reset(session: AsyncSession) -> None:
    await session.execute(text(f"TRUNCATE {', '.join(DEMO_TABLES)} RESTART IDENTITY CASCADE"))


async def _by_code(session: AsyncSession) -> dict[str, Language]:
    result = await session.execute(select(Language))
    return {language.code: language for language in result.scalars()}


async def _districts(session: AsyncSession) -> dict[tuple[str, str], District]:
    """Keyed by (region name, district name) — district names repeat across regions."""
    result = await session.execute(
        select(Region.name, District).join(District, District.region_id == Region.id)
    )
    return {(region, district.name): district for region, district in result.all()}


async def _amenities(session: AsyncSession) -> dict[str, Amenity]:
    result = await session.execute(select(Amenity))
    return {amenity.slug: amenity for amenity in result.scalars()}


async def _service_catalog(session: AsyncSession) -> dict[str, ServiceCatalog]:
    result = await session.execute(select(ServiceCatalog))
    return {entry.slug: entry for entry in result.scalars()}


async def _staff_roles(session: AsyncSession) -> dict[str, StaffRole]:
    result = await session.execute(select(StaffRole))
    return {role.slug: role for role in result.scalars()}


async def _make_user(
    session: AsyncSession,
    *,
    index: int,
    first_name: str,
    last_name: str,
    language: Language,
    role: UserRole,
    password_hash: str,
    district: District | None = None,
    email: str | None = None,
    login: str | None = None,
    theme: UserTheme = UserTheme.SYSTEM,
) -> User:
    user = User(
        first_name=first_name,
        last_name=last_name,
        phone=_phone(index),
        email=email,
        language_id=language.id,
        district_id=district.id if district else None,
        role=role,
        status=UserStatus.ACTIVE,
        theme=theme,
        login=login,
        password_hash=password_hash,
        must_change_password=False,
        last_login_at=utcnow_naive(),
    )
    session.add(user)
    await session.flush()
    return user


async def _make_working_hours(
    session: AsyncSession, venue: Venue, opens_at: time, closes_at: time, closed_weekday: int | None
) -> None:
    """Seven rows per branch — weekday 0 is Monday, matching the onboarding writer."""
    for weekday in range(7):
        is_closed = weekday == closed_weekday
        session.add(
            VenueWorkingHours(
                venue_id=venue.id,
                weekday=weekday,
                opens_at=None if is_closed else opens_at,
                closes_at=None if is_closed else closes_at,
                is_closed=is_closed,
            )
        )
    await session.flush()


async def _make_zones(session: AsyncSession, venue: Venue) -> list[VenueZone]:
    zones = [
        VenueZone(venue_id=venue.id, slug="ichkari", name="Ichkari", sort_order=1, is_active=True),
        VenueZone(
            venue_id=venue.id, slug="tashqari", name="Tashqari", sort_order=2, is_active=True
        ),
    ]
    session.add_all(zones)
    await session.flush()
    return zones


async def _make_tables(
    session: AsyncSession, venue: Venue, zones: Sequence[VenueZone], seat_plan: Sequence[int]
) -> list[VenueTable]:
    """`seat_plan` is the expanded onboarding bucket list — one entry per table."""
    tables = [
        VenueTable(
            venue_id=venue.id,
            number=number,
            seats=seats,
            zone_id=zones[(number - 1) % len(zones)].id,
            is_active=True,
        )
        for number, seats in enumerate(seat_plan, start=1)
    ]
    session.add_all(tables)
    await session.flush()
    return tables


async def _make_photos(session: AsyncSession, venue: Venue, count: int) -> None:
    for order in range(count):
        session.add(
            VenuePhoto(
                venue_id=venue.id,
                url=f"{PHOTO_BASE}/venue-{venue.id}-{order}/1200/800",
                sort_order=order,
                is_cover=order == 0,
            )
        )
    await session.flush()


async def _make_venue(
    session: AsyncSession,
    *,
    group: VenueGroup,
    district: District,
    name: str,
    venue_type: VenueTypeSlug,
    street: str,
    house_number: str,
    latitude: str,
    longitude: str,
    phone: str,
    description: str,
    tagline: str,
    total_seats: int | None = None,
    capacity_min: int | None = None,
    capacity_max: int | None = None,
    base_price: Decimal | None = None,
    requires_deposit: bool = False,
    deposit_percent: Decimal | None = None,
    discount_percent: Decimal | None = None,
    status: VenueStatus = VenueStatus.ACTIVE,
) -> Venue:
    venue = Venue(
        venue_group_id=group.id,
        owner_id=group.owner_id,
        district_id=district.id,
        venue_type=venue_type,
        street=street,
        house_number=house_number,
        latitude=Decimal(latitude),
        longitude=Decimal(longitude),
        phone=phone,
        total_seats=total_seats,
        capacity_min=capacity_min,
        capacity_max=capacity_max,
        base_price=base_price,
        currency="UZS",
        min_advance_booking_days=1,
        late_grace_minutes=40,
        requires_deposit=requires_deposit,
        deposit_percent=deposit_percent,
        discount_percent=discount_percent,
        rating_avg=Decimal("0.0"),
        reviews_count=0,
        status=status,
        onboarding_step=6,
        onboarded_at=utcnow_naive(),
        name=name,
        description=description,
        tagline=tagline,
    )
    session.add(venue)
    await session.flush()
    return venue


async def _make_booking(
    session: AsyncSession,
    *,
    user: User,
    venue: Venue,
    kind: BookingKind,
    booking_date: date,
    start_time: time,
    end_time: time,
    guests_count: int,
    status: BookingStatus,
    sequence: int,
    table: VenueTable | None = None,
    guest_tier: VenueGuestTier | None = None,
    venue_service: VenueService | None = None,
    subtotal: Decimal = Decimal("0.00"),
    deposit_amount: Decimal = Decimal("0.00"),
    note: str | None = None,
) -> Booking:
    now = utcnow_naive()
    booking = Booking(
        user_id=user.id,
        venue_id=venue.id,
        kind=kind,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        guests_count=guests_count,
        status=status,
        contact_name=f"{user.first_name} {user.last_name}",
        contact_phone=user.phone or _phone(0),
        note=note,
        subtotal=subtotal,
        deposit_amount=deposit_amount,
        deposit_paid_at=now if deposit_amount else None,
        total_amount=subtotal,
        currency="UZS",
        receipt_number=f"BZ-{booking_date:%Y%m%d}-{sequence:04d}",
        ticket_code=f"TKT{sequence:05d}",
        qr_token=f"demo-qr-token-{sequence:05d}",
        table_id=table.id if table else None,
        guest_tier_id=guest_tier.id if guest_tier else None,
        venue_service_id=venue_service.id if venue_service else None,
        confirmed_at=now
        if status in (BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN, BookingStatus.COMPLETED)
        else None,
        checked_in_at=now
        if status in (BookingStatus.CHECKED_IN, BookingStatus.COMPLETED)
        else None,
        completed_at=now if status == BookingStatus.COMPLETED else None,
        cancelled_at=now if status == BookingStatus.CANCELLED else None,
        cancel_reason="Mijoz rejasini o'zgartirdi" if status == BookingStatus.CANCELLED else None,
    )
    session.add(booking)
    await session.flush()

    session.add(
        BookingStatusHistory(
            booking_id=booking.id,
            from_status=None,
            to_status=status,
            changed_by_user_id=user.id,
            comment="Demo ma'lumot",
        )
    )
    await session.flush()
    return booking


async def seed(session: AsyncSession) -> None:
    """Write the whole demo layer. One transaction — the caller commits."""
    await _reset(session)

    languages = await _by_code(session)
    districts = await _districts(session)
    amenities = await _amenities(session)
    catalog = await _service_catalog(session)
    roles = await _staff_roles(session)

    uz, ru, en = languages["uz"], languages["ru"], languages["en"]

    # Hashed once and shared: PBKDF2 at 240k rounds costs ~0.1s, and a demo
    # account gains nothing from a per-user salt.
    password_hash = hash_secret(DEMO_PASSWORD)

    chilonzor = districts[("Toshkent shahri", "Chilonzor tumani")]
    yunusobod = districts[("Toshkent shahri", "Yunusobod tumani")]
    mirzo_ulugbek = districts[("Toshkent shahri", "Mirzo Ulug'bek tumani")]
    sirgali = districts[("Toshkent shahri", "Sirg'ali tumani")]
    yashnobod = districts[("Toshkent shahri", "Yashnobod tumani")]
    samarqand = districts[("Samarqand", "Samarqand shahri")]

    # --- people ---------------------------------------------------------------
    admin = await _make_user(
        session,
        index=1,
        first_name="Admin",
        last_name="Adminov",
        language=uz,
        role=UserRole.ADMIN,
        password_hash=password_hash,
        email="admin@bazfind.uz",
        login="bzadmin01",
        theme=UserTheme.DARK,
    )
    await _make_user(
        session,
        index=2,
        first_name="Malika",
        last_name="Yusupova",
        language=uz,
        role=UserRole.MODERATOR,
        password_hash=password_hash,
        email="moderator@bazfind.uz",
        login="bzmoder01",
    )

    sardor = await _make_user(
        session,
        index=11,
        first_name="Sardor",
        last_name="Rasulov",
        language=uz,
        role=UserRole.VENUE_OWNER,
        password_hash=password_hash,
        district=chilonzor,
        email="sardor@bahor.uz",
    )
    nodira = await _make_user(
        session,
        index=12,
        first_name="Nodira",
        last_name="Karimova",
        language=ru,
        role=UserRole.VENUE_OWNER,
        password_hash=password_hash,
        district=samarqand,
        email="nodira@registon.uz",
    )
    jasur = await _make_user(
        session,
        index=13,
        first_name="Jasur",
        last_name="Toshmatov",
        language=uz,
        role=UserRole.VENUE_OWNER,
        password_hash=password_hash,
        district=sirgali,
        email="jasur@zarafshon.uz",
    )

    customers = [
        await _make_user(
            session,
            index=101 + offset,
            first_name=first_name,
            last_name=last_name,
            language=language,
            role=UserRole.CUSTOMER,
            password_hash=password_hash,
            district=district,
            theme=theme,
        )
        for offset, (first_name, last_name, language, district, theme) in enumerate(
            [
                ("Aziz", "Umarov", uz, chilonzor, UserTheme.SYSTEM),
                ("Kamola", "Tursunova", uz, yunusobod, UserTheme.LIGHT),
                ("Dilshod", "Ergashev", ru, mirzo_ulugbek, UserTheme.DARK),
                ("Sevara", "Nazarova", en, yashnobod, UserTheme.SYSTEM),
                ("Bekzod", "Olimov", uz, sirgali, UserTheme.LIGHT),
                ("Zilola", "Hakimova", ru, samarqand, UserTheme.SYSTEM),
            ]
        )
    ]

    # --- chains ---------------------------------------------------------------
    bahor = VenueGroup(
        owner_id=sardor.id,
        primary_venue_type=VenueTypeSlug.RESTORAN,
        logo_url=f"{PHOTO_BASE}/bahor-logo/256/256",
        default_currency="UZS",
        status=VenueGroupStatus.ACTIVE,
        name="Bahor Restoranlari",
        description="Toshkentdagi milliy va Yevropa taomlari tarmog'i.",
    )
    registon = VenueGroup(
        owner_id=nodira.id,
        primary_venue_type=VenueTypeSlug.RESTORAN,
        logo_url=f"{PHOTO_BASE}/registon-logo/256/256",
        default_currency="UZS",
        status=VenueGroupStatus.ACTIVE,
        name="Registon Osh Markazi",
        description="Samarqand oshi va tandir taomlari.",
    )
    zarafshon = VenueGroup(
        owner_id=jasur.id,
        primary_venue_type=VenueTypeSlug.TOYXONA,
        logo_url=f"{PHOTO_BASE}/zarafshon-logo/256/256",
        default_currency="UZS",
        status=VenueGroupStatus.ACTIVE,
        name="Zarafshon To'yxonalari",
        description="To'y va katta tadbirlar uchun zallar.",
    )
    session.add_all([bahor, registon, zarafshon])
    await session.flush()

    # --- branches -------------------------------------------------------------
    bahor_chilonzor = await _make_venue(
        session,
        group=bahor,
        district=chilonzor,
        name="Bahor Chilonzor",
        venue_type=VenueTypeSlug.RESTORAN,
        street="Bunyodkor shoh ko'chasi",
        house_number="12",
        latitude="41.275300",
        longitude="69.203900",
        phone="+998712001101",
        description="Chilonzordagi asosiy filial, ochiq terrasa bilan.",
        tagline="Milliy taomlar va tandir",
        total_seats=96,
        discount_percent=Decimal("10.00"),
    )
    bahor_yunusobod = await _make_venue(
        session,
        group=bahor,
        district=yunusobod,
        name="Bahor Yunusobod",
        venue_type=VenueTypeSlug.RESTORAN,
        street="Amir Temur shoh ko'chasi",
        house_number="108",
        latitude="41.351600",
        longitude="69.289700",
        phone="+998712001102",
        description="Biznes-lanch va oilaviy kechki ovqat uchun filial.",
        tagline="Shahar markazida",
        total_seats=72,
    )
    registon_toshkent = await _make_venue(
        session,
        group=registon,
        district=mirzo_ulugbek,
        name="Registon Mirzo Ulug'bek",
        venue_type=VenueTypeSlug.RESTORAN,
        street="Buyuk Ipak Yo'li ko'chasi",
        house_number="45",
        latitude="41.325400",
        longitude="69.334200",
        phone="+998712001103",
        description="Samarqand oshxonasi Toshkentda.",
        tagline="Haqiqiy Samarqand oshi",
        total_seats=64,
    )
    registon_samarqand = await _make_venue(
        session,
        group=registon,
        district=samarqand,
        name="Registon Samarqand",
        venue_type=VenueTypeSlug.RESTORAN,
        street="Registon ko'chasi",
        house_number="7",
        latitude="39.654800",
        longitude="66.975700",
        phone="+998662001104",
        description="Registon maydoni yonidagi bosh filial.",
        tagline="Tarixiy markazda",
        total_seats=120,
    )
    zarafshon_sirgali = await _make_venue(
        session,
        group=zarafshon,
        district=sirgali,
        name="Zarafshon To'yxonasi Sirg'ali",
        venue_type=VenueTypeSlug.TOYXONA,
        street="Yangi Sergeli ko'chasi",
        house_number="3",
        latitude="41.220700",
        longitude="69.216800",
        phone="+998712001105",
        description="300 kishilik asosiy zal va avtoturargoh.",
        tagline="Katta to'ylar uchun",
        capacity_min=100,
        capacity_max=400,
        base_price=Decimal("45000000.00"),
        requires_deposit=True,
        deposit_percent=Decimal("20.00"),
    )
    zarafshon_yashnobod = await _make_venue(
        session,
        group=zarafshon,
        district=yashnobod,
        name="Zarafshon To'yxonasi Yashnobod",
        venue_type=VenueTypeSlug.TOYXONA,
        street="Mahtumquli ko'chasi",
        house_number="21",
        latitude="41.288900",
        longitude="69.329100",
        phone="+998712001106",
        description="Kichikroq zal, nikoh to'ylari va yubileylar uchun.",
        tagline="Yaqin doiradagi tadbirlar",
        capacity_min=80,
        capacity_max=250,
        base_price=Decimal("28000000.00"),
        requires_deposit=True,
        deposit_percent=Decimal("15.00"),
        status=VenueStatus.PENDING,
    )

    restaurants = [bahor_chilonzor, bahor_yunusobod, registon_toshkent, registon_samarqand]
    halls = [zarafshon_sirgali, zarafshon_yashnobod]

    # --- working hours, zones, tables, photos, amenities ----------------------
    for venue in restaurants:
        await _make_working_hours(session, venue, time(10, 0), time(23, 0), closed_weekday=None)
        zones = await _make_zones(session, venue)
        await _make_tables(session, venue, zones, [2, 2, 4, 4, 4, 4, 6, 6, 6, 8, 8, 10])
        await _make_photos(session, venue, 3)

    for venue in halls:
        await _make_working_hours(session, venue, time(11, 0), time(23, 30), closed_weekday=0)
        await _make_photos(session, venue, 4)

    venue_amenities = {
        bahor_chilonzor.id: ["parking", "wifi", "air_conditioning", "professional_kitchen"],
        bahor_yunusobod.id: ["wifi", "air_conditioning"],
        registon_toshkent.id: ["parking", "wifi", "professional_kitchen"],
        registon_samarqand.id: ["parking", "air_conditioning", "professional_kitchen"],
        zarafshon_sirgali.id: ["parking", "sound_system", "stage", "air_conditioning"],
        zarafshon_yashnobod.id: ["parking", "sound_system", "stage"],
    }
    for venue_id, slugs in venue_amenities.items():
        for slug in slugs:
            session.add(VenueAmenity(venue_id=venue_id, amenity_id=amenities[slug].id))
    await session.flush()

    # --- guest tiers (to'yxona only) -----------------------------------------
    tiers: dict[int, list[VenueGuestTier]] = {}
    for venue, prices in (
        (zarafshon_sirgali, ["45000000.00", "58000000.00", "72000000.00", "95000000.00"]),
        (zarafshon_yashnobod, ["28000000.00", "36000000.00", "45000000.00", "60000000.00"]),
    ):
        bands: list[tuple[int, int | None]] = [(100, 150), (150, 200), (200, 300), (300, None)]
        rows = [
            VenueGuestTier(
                venue_id=venue.id,
                min_guests=min_guests,
                max_guests=max_guests,
                base_price=Decimal(price),
                sort_order=order,
            )
            for order, ((min_guests, max_guests), price) in enumerate(
                zip(bands, prices, strict=True), start=1
            )
        ]
        session.add_all(rows)
        await session.flush()
        tiers[venue.id] = rows

    # --- chain services -------------------------------------------------------
    dasturxon = VenueService(
        venue_group_id=zarafshon.id,
        venue_id=None,
        service_catalog_id=catalog["dasturxon_tuzash"].id,
        price=Decimal("85000.00"),
        currency="UZS",
        price_unit=ServicePriceUnit.PER_GUEST,
        is_active=True,
        sort_order=1,
    )
    session.add(dasturxon)
    await session.flush()

    for order, (item_name, item_price) in enumerate(
        [
            ("Osh", Decimal("35000.00")),
            ("Norin", Decimal("28000.00")),
            ("Somsa", Decimal("12000.00")),
            ("Mevalar to'plami", Decimal("18000.00")),
            ("Shirinliklar to'plami", Decimal("15000.00")),
        ],
        start=1,
    ):
        session.add(
            VenueServiceItem(
                venue_service_id=dasturxon.id,
                name=item_name,
                price=item_price,
                sort_order=order,
            )
        )

    for order, (slug, price, unit) in enumerate(
        [
            ("raqqoslar", Decimal("3500000.00"), ServicePriceUnit.FLAT),
            ("qoshiqchi", Decimal("8000000.00"), ServicePriceUnit.FLAT),
            ("video", Decimal("5500000.00"), ServicePriceUnit.FLAT),
            ("sahna", Decimal("2500000.00"), ServicePriceUnit.FLAT),
            ("kartej", Decimal("4000000.00"), ServicePriceUnit.FLAT),
        ],
        start=2,
    ):
        session.add(
            VenueService(
                venue_group_id=zarafshon.id,
                venue_id=None,
                service_catalog_id=catalog[slug].id,
                price=price,
                currency="UZS",
                price_unit=unit,
                is_active=True,
                sort_order=order,
            )
        )
    await session.flush()

    # --- menus ----------------------------------------------------------------
    menu_by_group: dict[int, list[MenuItem]] = {}
    menus: dict[int, list[tuple[str, list[tuple[str, str | None, str | None]]]]] = {
        bahor.id: [
            (
                "Milliy taomlar",
                [
                    ("Osh", None, "Toshkent oshi, qazi va danak bilan"),
                    ("Norin", "42000.00", "Qo'l kesim norin"),
                    ("Manti", "38000.00", "Bug'da pishirilgan qo'y go'shtli manti"),
                    ("Lag'mon", "40000.00", "Qo'lda cho'zilgan lag'mon"),
                ],
            ),
            (
                "Salatlar",
                [
                    ("Achichuk", "18000.00", "Pomidor, piyoz, achchiq qalampir"),
                    ("Sezar", "46000.00", "Tovuq va parmezan bilan"),
                ],
            ),
            (
                "Ichimliklar",
                [
                    ("Ko'k choy", "8000.00", None),
                    ("Limonli choy", "12000.00", None),
                    ("Kompot", "14000.00", None),
                ],
            ),
            ("Shirinliklar", [("Chak-chak", "22000.00", None), ("Muzqaymoq", "20000.00", None)]),
        ],
        registon.id: [
            (
                "Tandir taomlari",
                [
                    ("Tandir go'sht", "95000.00", "Tandirda pishirilgan qo'y go'shti"),
                    ("Samsa", "15000.00", "Tandir samsa"),
                ],
            ),
            (
                "Osh turlari",
                [
                    ("Samarqand oshi", "55000.00", None),
                    ("Chayonli osh", "62000.00", None),
                ],
            ),
            ("Ichimliklar", [("Choy", "7000.00", None), ("Ayron", "13000.00", None)]),
        ],
    }

    for group_id, categories in menus.items():
        group_items: list[MenuItem] = []
        for category_order, (category_name, items) in enumerate(categories, start=1):
            category = MenuCategory(
                venue_group_id=group_id,
                sort_order=category_order,
                is_active=True,
                name=category_name,
            )
            session.add(category)
            await session.flush()

            for item_order, (item_name, base_price, description) in enumerate(items, start=1):
                item = MenuItem(
                    menu_category_id=category.id,
                    base_price=Decimal(base_price) if base_price else None,
                    currency="UZS",
                    photo_url=f"{PHOTO_BASE}/dish-{group_id}-{category_order}-{item_order}/600/400",
                    is_available=True,
                    sort_order=item_order,
                    has_variants=base_price is None,
                    status=MenuItemStatus.ACTIVE,
                    name=item_name,
                    description=description,
                )
                session.add(item)
                await session.flush()
                group_items.append(item)

                if base_price is None:
                    # "Osh" is the one dish sold by portion — variants replace the
                    # base price, they never sit beside it.
                    session.add_all(
                        [
                            MenuItemVariant(
                                menu_item_id=item.id,
                                price=Decimal("30000.00"),
                                sort_order=1,
                                is_active=True,
                                name="Yarim porsiya",
                            ),
                            MenuItemVariant(
                                menu_item_id=item.id,
                                price=Decimal("48000.00"),
                                sort_order=2,
                                is_active=True,
                                name="To'liq porsiya",
                            ),
                        ]
                    )
                    await session.flush()
        menu_by_group[group_id] = group_items

    for venue in restaurants:
        for item in menu_by_group[venue.venue_group_id]:
            session.add(
                MenuItemBranch(
                    menu_item_id=item.id,
                    venue_id=venue.id,
                    is_available=True,
                    # The Samarqand branch runs 10% cheaper than the Tashkent one.
                    price_override=(
                        (item.base_price * Decimal("0.9")).quantize(Decimal("0.01"))
                        if venue.id == registon_samarqand.id and item.base_price is not None
                        else None
                    ),
                )
            )
    await session.flush()

    # --- staff ----------------------------------------------------------------
    staff_by_venue: dict[int, dict[str, VenueStaff]] = {}
    staff_index = 200
    for venue, group in (
        (bahor_chilonzor, bahor),
        (bahor_yunusobod, bahor),
        (registon_toshkent, registon),
        (registon_samarqand, registon),
        (zarafshon_sirgali, zarafshon),
        (zarafshon_yashnobod, zarafshon),
    ):
        venue_staff: dict[str, VenueStaff] = {}
        for role_slug, first_name, last_name in (
            ("manager", "Otabek", "Sultonov"),
            ("waiter", "Nilufar", "Qodirova"),
            ("cook", "Rustam", "Ismoilov"),
        ):
            staff_index += 1
            employee = await _make_user(
                session,
                index=staff_index,
                first_name=first_name,
                last_name=last_name,
                language=uz,
                role=UserRole.VENUE_STAFF,
                password_hash=password_hash,
                login=f"bz{role_slug[:4]}{staff_index}",
            )
            role = roles[role_slug]
            employment = VenueStaff(
                venue_group_id=group.id,
                venue_id=venue.id,
                user_id=employee.id,
                staff_role_id=role.id,
                role_scope=role.scope,
                is_active=True,
                invited_by_user_id=group.owner_id,
                invited_at=utcnow_naive(),
                activated_at=utcnow_naive(),
            )
            session.add(employment)
            await session.flush()
            venue_staff[role_slug] = employment
        staff_by_venue[venue.id] = venue_staff

    # Owners hold a group-scoped employment row with no branch.
    for group in (bahor, registon, zarafshon):
        owner_role = roles["owner"]
        session.add(
            VenueStaff(
                venue_group_id=group.id,
                venue_id=None,
                user_id=group.owner_id,
                staff_role_id=owner_role.id,
                role_scope=owner_role.scope,
                is_active=True,
                invited_at=utcnow_naive(),
                activated_at=utcnow_naive(),
            )
        )
    await session.flush()

    # --- bookings -------------------------------------------------------------
    today = date.today()
    tables_result = await session.execute(
        select(VenueTable).where(VenueTable.venue_id.in_([v.id for v in restaurants]))
    )
    tables_by_venue: dict[int, list[VenueTable]] = {}
    for table in tables_result.scalars():
        tables_by_venue.setdefault(table.venue_id, []).append(table)

    bookings: list[Booking] = []
    sequence = 0
    reservation_plan: list[tuple[Venue, int, BookingStatus, int, int]] = [
        # venue, table index, status, day offset, start hour
        (bahor_chilonzor, 0, BookingStatus.CONFIRMED, 1, 19),
        (bahor_chilonzor, 1, BookingStatus.PENDING, 1, 20),
        (bahor_chilonzor, 2, BookingStatus.COMPLETED, -3, 19),
        (bahor_yunusobod, 0, BookingStatus.CONFIRMED, 2, 18),
        (bahor_yunusobod, 3, BookingStatus.CANCELLED, 2, 19),
        (registon_toshkent, 0, BookingStatus.CHECKED_IN, 0, 13),
        (registon_toshkent, 4, BookingStatus.COMPLETED, -7, 20),
        (registon_samarqand, 0, BookingStatus.CONFIRMED, 3, 19),
    ]
    for offset, (venue, table_index, status, day_offset, hour) in enumerate(reservation_plan):
        sequence += 1
        table = tables_by_venue[venue.id][table_index]
        bookings.append(
            await _make_booking(
                session,
                user=customers[offset % len(customers)],
                venue=venue,
                kind=BookingKind.TABLE_RESERVATION,
                booking_date=today + timedelta(days=day_offset),
                start_time=time(hour, 0),
                end_time=time(hour + 2, 0),
                guests_count=table.seats,
                status=status,
                sequence=sequence,
                table=table,
                subtotal=Decimal("0.00"),
                note="Deraza yonidagi stol bo'lsa yaxshi" if table_index == 0 else None,
            )
        )

    hall_plan: list[tuple[Venue, BookingStatus, int, int]] = [
        (zarafshon_sirgali, BookingStatus.CONFIRMED, 21, 250),
        (zarafshon_sirgali, BookingStatus.PENDING, 45, 180),
        (zarafshon_sirgali, BookingStatus.COMPLETED, -30, 300),
        (zarafshon_yashnobod, BookingStatus.CONFIRMED, 14, 120),
    ]
    for offset, (venue, status, day_offset, guests) in enumerate(hall_plan):
        sequence += 1
        tier = next(
            row
            for row in tiers[venue.id]
            if row.min_guests <= guests and (row.max_guests is None or guests <= row.max_guests)
        )
        catering = tier.base_price + dasturxon.price * guests
        deposit = (catering * (venue.deposit_percent or Decimal("0")) / Decimal("100")).quantize(
            Decimal("0.01")
        )
        booking = await _make_booking(
            session,
            user=customers[(offset + 2) % len(customers)],
            venue=venue,
            kind=BookingKind.HALL_EVENT,
            booking_date=today + timedelta(days=day_offset),
            start_time=time(11, 0),
            end_time=time(16, 0),
            guests_count=guests,
            status=status,
            sequence=sequence,
            guest_tier=tier,
            venue_service=dasturxon,
            subtotal=catering,
            deposit_amount=deposit if status != BookingStatus.PENDING else Decimal("0.00"),
            note="Nikoh to'yi",
        )
        session.add(
            BookingService(
                booking_id=booking.id,
                venue_service_id=dasturxon.id,
                quantity=guests,
                unit_price=dasturxon.price,
                name_snapshot=catalog["dasturxon_tuzash"].name,
                total_price=dasturxon.price * guests,
            )
        )
        session.add_all(
            [
                BookingPriceLine(
                    booking_id=booking.id,
                    sort_order=1,
                    line_type=PriceLineType.HALL_RENTAL,
                    label_snapshot=f"Zal ijarasi ({guests} mehmon)",
                    unit_price=tier.base_price,
                    quantity=1,
                    amount=tier.base_price,
                ),
                BookingPriceLine(
                    booking_id=booking.id,
                    sort_order=2,
                    line_type=PriceLineType.CATERING,
                    label_snapshot=catalog["dasturxon_tuzash"].name,
                    unit_price=dasturxon.price,
                    quantity=guests,
                    amount=dasturxon.price * guests,
                ),
            ]
        )
        bookings.append(booking)
    await session.flush()

    # --- orders ---------------------------------------------------------------
    bahor_items = menu_by_group[bahor.id]
    for order_number, (venue, table_index, order_status) in enumerate(
        [
            (bahor_chilonzor, 5, OrderStatus.OPEN),
            (bahor_chilonzor, 6, OrderStatus.IN_PROGRESS),
            (bahor_yunusobod, 5, OrderStatus.COMPLETED),
        ],
        start=1,
    ):
        closed = order_status == OrderStatus.COMPLETED
        staff = staff_by_venue[venue.id]
        table = tables_by_venue[venue.id][table_index]
        check = Order(
            venue_id=venue.id,
            table_id=table.id,
            order_number=order_number,
            business_date=today,
            kind=OrderKind.DINE_IN,
            status=order_status,
            guests_count=table.seats,
            waiter_staff_id=staff["waiter"].id,
            opened_by_staff_id=staff["manager"].id,
            closed_by_staff_id=staff["manager"].id if closed else None,
            currency="UZS",
            opened_at=utcnow_naive(),
            closed_at=utcnow_naive() if closed else None,
        )
        session.add(check)
        await session.flush()

        subtotal = Decimal("0.00")
        for line, item in enumerate(bahor_items[1:4], start=1):
            unit_price = item.base_price or Decimal("48000.00")
            total_price = unit_price * line
            subtotal += total_price
            session.add(
                OrderItem(
                    order_id=check.id,
                    menu_item_id=item.id,
                    quantity=line,
                    unit_price=unit_price,
                    total_price=total_price,
                    name_snapshot=item.name,
                    status=(
                        OrderItemStatus.SENT_TO_KITCHEN
                        if order_status == OrderStatus.OPEN
                        else OrderItemStatus.SERVED
                    ),
                    added_by_staff_id=staff["waiter"].id,
                    added_at=utcnow_naive(),
                )
            )
        check.subtotal = subtotal
        check.total_amount = subtotal
    await session.flush()

    # --- reviews and favourites ----------------------------------------------
    completed = [b for b in bookings if b.status == BookingStatus.COMPLETED]
    review_texts = [
        (5, "Xizmat ham, taom ham a'lo darajada. Yana boramiz."),
        (4, "Osh juda mazali edi, lekin biroz kutishga to'g'ri keldi."),
        (5, "To'y zali keng, ovoz tizimi zo'r. Rahmat!"),
    ]
    for offset, booking in enumerate(completed):
        rating, comment = review_texts[offset % len(review_texts)]
        session.add(
            Review(
                user_id=booking.user_id,
                venue_id=booking.venue_id,
                booking_id=booking.id,
                rating=rating,
                comment=comment,
                is_verified=True,
                status=ReviewStatus.PUBLISHED,
                published_at=utcnow_naive(),
            )
        )

    unverified = [
        (bahor_chilonzor, customers[3], 4, "Terrasa yoqdi, narxlar o'rtacha."),
        (registon_toshkent, customers[4], 5, "Tandir go'sht bo'yicha eng yaxshi joy."),
        (zarafshon_sirgali, customers[5], 4, "Avtoturargoh kichikroq, qolgani yaxshi."),
    ]
    for venue, user, rating, comment in unverified:
        session.add(
            Review(
                user_id=user.id,
                venue_id=venue.id,
                booking_id=None,
                rating=rating,
                comment=comment,
                is_verified=False,
                status=ReviewStatus.PUBLISHED,
                published_at=utcnow_naive(),
            )
        )
    await session.flush()

    # `rating_avg` / `reviews_count` are denormalized counters — recomputed here
    # through the ORM so `updated_at` moves with them.
    for venue in restaurants + halls:
        result = await session.execute(
            select(Review.rating).where(
                Review.venue_id == venue.id, Review.status == ReviewStatus.PUBLISHED
            )
        )
        ratings = list(result.scalars())
        venue.reviews_count = len(ratings)
        venue.rating_avg = (
            (Decimal(sum(ratings)) / Decimal(len(ratings))).quantize(Decimal("0.1"))
            if ratings
            else Decimal("0.0")
        )

    for user, venue in (
        (customers[0], bahor_chilonzor),
        (customers[0], zarafshon_sirgali),
        (customers[1], registon_toshkent),
        (customers[2], bahor_yunusobod),
        (customers[3], registon_samarqand),
    ):
        session.add(Favorite(user_id=user.id, venue_id=venue.id))
    await session.flush()

    print(f"admin       {admin.phone} / {DEMO_PASSWORD}")
    print(f"owners      {sardor.phone}, {nodira.phone}, {jasur.phone}")
    print(f"customers   {customers[0].phone} .. {customers[-1].phone}")
    print(f"venues      {len(restaurants) + len(halls)}")
    print(f"bookings    {len(bookings)}")


async def main() -> None:
    if settings.env is not AppEnv.LOCAL:
        print(f"refusing to seed demo data with ENV={settings.env}", file=sys.stderr)
        raise SystemExit(1)

    engine = create_async_engine(str(settings.database.url))
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        await seed(session)
        await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
