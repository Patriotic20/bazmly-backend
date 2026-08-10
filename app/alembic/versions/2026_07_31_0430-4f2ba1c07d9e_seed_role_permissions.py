"""seed role permissions

Revision ID: 4f2ba1c07d9e
Revises: 73548a20054d
Create Date: 2026-07-31 04:30:00.000000

Data-only revision, and the one that makes the API usable at all.

`b7834c92fef5` seeded `staff_roles` and `permissions` but never the table that
joins them, so `VenueStaffRepository.has_permission` — one join through
`staff_role_permissions` — returned false for every user, every branch, every
slug. Every `require_permission` route answered 403 on a freshly migrated
database, including for the owner.

Kept as a separate revision rather than an edit to `b7834c92fef5`, which may
already be applied.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f2ba1c07d9e"
down_revision: str | Sequence[str] | None = "73548a20054d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Who may do what. Two rules shape this:
#
# `branch.create` belongs to the group scope only — opening a branch is a
# contract and a bill, not a shift decision, so a `manager` cannot do it.
#
# `settings.edit` is the owner's alone: it moves the logo and the currency, which
# are brand-level and chain-wide.
ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "owner": (
        "branch.manage",
        "branch.create",
        "staff.manage",
        "menu.edit",
        "menu.publish",
        "orders.open",
        "orders.add_items",
        "orders.close",
        "orders.discount",
        "bookings.confirm",
        "bookings.cancel",
        "reports.view",
        "settings.edit",
    ),
    "admin": (
        "branch.manage",
        "branch.create",
        "staff.manage",
        "menu.edit",
        "menu.publish",
        "orders.open",
        "orders.add_items",
        "orders.close",
        "orders.discount",
        "bookings.confirm",
        "bookings.cancel",
        "reports.view",
    ),
    "manager": (
        "branch.manage",
        "staff.manage",
        "menu.edit",
        "menu.publish",
        "orders.open",
        "orders.add_items",
        "orders.close",
        "orders.discount",
        "bookings.confirm",
        "bookings.cancel",
        "reports.view",
    ),
    "waiter": (
        "orders.open",
        "orders.add_items",
        "orders.close",
        "bookings.confirm",
    ),
    "cook": ("orders.add_items",),
    "cook_assistant": ("orders.add_items",),
    "security": ("bookings.confirm",),
}


def _q(value: str) -> str:
    """Single-quote a literal for inline SQL."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def upgrade() -> None:
    """Upgrade schema."""
    for role_slug, permission_slugs in ROLE_PERMISSIONS.items():
        for permission_slug in permission_slugs:
            # Joined on slug rather than id: both tables are seeded by an earlier
            # revision and their surrogate keys are not ours to predict.
            op.execute(
                "INSERT INTO staff_role_permissions (staff_role_id, permission_id) "
                "SELECT sr.id, p.id FROM staff_roles sr, permissions p "
                f"WHERE sr.slug = {_q(role_slug)} AND p.slug = {_q(permission_slug)}"
            )


def downgrade() -> None:
    """Downgrade schema."""
    for role_slug, permission_slugs in ROLE_PERMISSIONS.items():
        slugs = ", ".join(_q(slug) for slug in permission_slugs)
        op.execute(
            "DELETE FROM staff_role_permissions WHERE staff_role_id IN "
            f"(SELECT id FROM staff_roles WHERE slug = {_q(role_slug)}) "
            f"AND permission_id IN (SELECT id FROM permissions WHERE slug IN ({slugs}))"
        )
