"""a to'yxona's default guest band spans its hall's capacity

The band a to'yxona was born with ran from one guest upwards at a hall price of
nothing, whatever range the owner gave — so the booking screen read "1+ kishi,
Zal narxi: 0 so'm" and accepted eleven guests for a 200-1000 hall. Onboarding
now creates it from `capacity_min`-`capacity_max`; this moves the bands already
made the same way.

Only a venue's lone, untouched default band is moved: one tier, from 1 guest,
open-ended. A band an owner shaped is left as it is. The downgrade cannot tell
moved bands from shaped ones, so it leaves them.

Revision ID: 7c3e1d9a2b4f
Revises: 4f2a9c1e7b3d
Create Date: 2026-10-28 20:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c3e1d9a2b4f"
down_revision: str | Sequence[str] | None = "4f2a9c1e7b3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        UPDATE venue_guest_tiers AS t
        SET min_guests = COALESCE(v.capacity_min, 1),
            max_guests = v.capacity_max
        FROM venues AS v
        WHERE t.venue_id = v.id
          AND v.venue_type = 'toyxona'
          AND (v.capacity_min IS NOT NULL OR v.capacity_max IS NOT NULL)
          AND t.min_guests = 1
          AND t.max_guests IS NULL
          AND (SELECT count(*) FROM venue_guest_tiers o WHERE o.venue_id = v.id) = 1
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
