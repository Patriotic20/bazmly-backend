"""dasturxon comes in two kinds: standart and premium

A to'yxona sells its table spread at two levels, each with its own price and
dishes. Two catalogue entries rather than a level column on `venue_services`:
the catalogue is already what the owner picks from, the booking flow already
treats each entry as its own priced line, and a branch can then offer one,
the other or both without any new shape.

The existing `dasturxon_tuzash` row becomes the standart one and keeps its
slug, so every price already set against it carries on unchanged. The downgrade
removes the premium row only when nothing has priced it.

Revision ID: 4f2a9c1e7b3d
Revises: 830e93ce29ac
Create Date: 2026-10-24 21:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f2a9c1e7b3d"
down_revision: str | Sequence[str] | None = "830e93ce29ac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "UPDATE service_catalog SET name = 'Dasturxon (Standart)' WHERE slug = 'dasturxon_tuzash'"
    )
    op.execute(
        "INSERT INTO service_catalog (slug, name, sort_order, is_active) "
        "SELECT 'dasturxon_premium', 'Dasturxon (Premium)', sort_order, true "
        "FROM service_catalog WHERE slug = 'dasturxon_tuzash' "
        "ON CONFLICT (slug) DO NOTHING"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DELETE FROM service_catalog WHERE slug = 'dasturxon_premium' AND NOT EXISTS ("
        "SELECT 1 FROM venue_services vs WHERE vs.service_catalog_id = service_catalog.id)"
    )
    op.execute(
        "UPDATE service_catalog SET name = 'Dasturxon tuzash' WHERE slug = 'dasturxon_tuzash'"
    )
