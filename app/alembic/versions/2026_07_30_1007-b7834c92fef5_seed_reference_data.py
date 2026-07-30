"""seed reference data

Data-only revision. Seeds the closed, platform-owned lists that the app cannot
function without: languages, venue types, staff roles, permissions, the service
catalog and amenities.

Kept as a migration rather than a `scripts/seed.py` so that a single
`alembic upgrade head` yields a usable database, and so the seed is versioned and
reversible alongside the schema it depends on.

Revision ID: b7834c92fef5
Revises: 69782ad47f79
Create Date: 2026-07-30

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7834c92fef5"
down_revision: str | Sequence[str] | None = "69782ad47f79"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LANGUAGES = [
    ("uz", "O'zbekcha", "Uzbek", True, 1),
    ("en", "English", "English", True, 2),
    ("ru", "Russian", "Russian", True, 3),
]

# slug -> Uzbek name
VENUE_TYPES = [
    ("restoran", "Restoran", 1),
    ("toyxona", "To'yxona", 2),
    ("kafe", "Kafe", 3),
]

# slug, scope, Uzbek name, sort order
STAFF_ROLES = [
    ("owner", "group", "Egasi", 1),
    ("admin", "group", "Admin", 2),
    ("manager", "venue", "Menendjer", 3),
    ("waiter", "venue", "Ofitsant", 4),
    ("cook", "venue", "Oshpaz", 5),
    ("cook_assistant", "venue", "Oshpaz yordamchisi", 6),
    ("security", "venue", "Qo'riqchi", 7),
]

# slug -> permission group
PERMISSIONS = [
    ("branch.manage", "branch"),
    ("branch.create", "branch"),
    ("staff.manage", "staff"),
    ("menu.edit", "menu"),
    ("menu.publish", "menu"),
    ("orders.open", "orders"),
    ("orders.add_items", "orders"),
    ("orders.close", "orders"),
    ("orders.discount", "orders"),
    ("bookings.confirm", "bookings"),
    ("bookings.cancel", "bookings"),
    ("reports.view", "reports"),
    ("settings.edit", "settings"),
]

# slug -> Uzbek name (Part 2, section 18)
SERVICE_CATALOG = [
    ("dasturxon_tuzash", "Dasturxon tuzash", 1),
    ("raqqoslar", "Raqqoslar", 2),
    ("kartej", "Kartej", 3),
    ("video", "Video", 4),
    ("qoshiqchi", "Qo'shiqchi", 5),
    ("sahna", "Sahna", 6),
]

AMENITIES = [
    ("parking", 1),
    ("sound_system", 2),
    ("stage", 3),
    ("air_conditioning", 4),
    ("professional_kitchen", 5),
    ("wifi", 6),
]


def _q(value: str) -> str:
    """Single-quote a literal for inline SQL."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def upgrade() -> None:
    """Upgrade schema."""
    for code, native, english, is_active, order in LANGUAGES:
        op.execute(
            "INSERT INTO languages (code, name_native, name_english, is_active, sort_order) "
            f"VALUES ({_q(code)}, {_q(native)}, {_q(english)}, {str(is_active).lower()}, {order})"
        )

    for slug, name, order in VENUE_TYPES:
        op.execute(
            "INSERT INTO venue_types (slug, sort_order, is_active) "
            f"VALUES ({_q(slug)}, {order}, true)"
        )
        op.execute(
            "INSERT INTO venue_type_translations (venue_type_id, language_id, name) "
            f"SELECT vt.id, l.id, {_q(name)} FROM venue_types vt, languages l "
            f"WHERE vt.slug = {_q(slug)} AND l.code = 'uz'"
        )

    for slug, scope, name, order in STAFF_ROLES:
        op.execute(
            "INSERT INTO staff_roles (slug, scope, is_system, sort_order, is_active) "
            f"VALUES ({_q(slug)}, {_q(scope)}, true, {order}, true)"
        )
        op.execute(
            "INSERT INTO staff_role_translations (staff_role_id, language_id, name) "
            f"SELECT sr.id, l.id, {_q(name)} FROM staff_roles sr, languages l "
            f"WHERE sr.slug = {_q(slug)} AND l.code = 'uz'"
        )

    for slug, group in PERMISSIONS:
        op.execute(f'INSERT INTO permissions (slug, "group") VALUES ({_q(slug)}, {_q(group)})')

    for slug, name, order in SERVICE_CATALOG:
        op.execute(
            "INSERT INTO service_catalog (slug, sort_order, is_active) "
            f"VALUES ({_q(slug)}, {order}, true)"
        )
        op.execute(
            "INSERT INTO service_catalog_translations (service_catalog_id, language_id, name) "
            f"SELECT sc.id, l.id, {_q(name)} FROM service_catalog sc, languages l "
            f"WHERE sc.slug = {_q(slug)} AND l.code = 'uz'"
        )

    for slug, order in AMENITIES:
        op.execute(f"INSERT INTO amenities (slug, sort_order) VALUES ({_q(slug)}, {order})")


def downgrade() -> None:
    """Downgrade schema."""
    amenity_slugs = ", ".join(_q(s) for s, _ in AMENITIES)
    service_slugs = ", ".join(_q(s) for s, _, _ in SERVICE_CATALOG)
    permission_slugs = ", ".join(_q(s) for s, _ in PERMISSIONS)
    role_slugs = ", ".join(_q(s) for s, _, _, _ in STAFF_ROLES)
    venue_type_slugs = ", ".join(_q(s) for s, _, _ in VENUE_TYPES)
    language_codes = ", ".join(_q(c) for c, _, _, _, _ in LANGUAGES)

    op.execute(f"DELETE FROM amenities WHERE slug IN ({amenity_slugs})")
    op.execute(
        "DELETE FROM service_catalog_translations WHERE service_catalog_id IN "
        f"(SELECT id FROM service_catalog WHERE slug IN ({service_slugs}))"
    )
    op.execute(f"DELETE FROM service_catalog WHERE slug IN ({service_slugs})")
    op.execute(f"DELETE FROM permissions WHERE slug IN ({permission_slugs})")
    op.execute(
        "DELETE FROM staff_role_translations WHERE staff_role_id IN "
        f"(SELECT id FROM staff_roles WHERE slug IN ({role_slugs}))"
    )
    op.execute(f"DELETE FROM staff_roles WHERE slug IN ({role_slugs})")
    op.execute(
        "DELETE FROM venue_type_translations WHERE venue_type_id IN "
        f"(SELECT id FROM venue_types WHERE slug IN ({venue_type_slugs}))"
    )
    op.execute(f"DELETE FROM venue_types WHERE slug IN ({venue_type_slugs})")
    op.execute(f"DELETE FROM languages WHERE code IN ({language_codes})")
