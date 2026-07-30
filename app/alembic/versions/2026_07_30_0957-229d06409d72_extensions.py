"""extensions

Creates the three Postgres extensions every later revision depends on:

- ``postgis``    — ``venues.location`` is ``geography(Point, 4326)``
- ``btree_gist`` — the ``bookings`` exclusion constraint mixes ``=`` on an int
  with ``&&`` on a range, which plain GiST cannot index
- ``pg_trgm``    — the GIN trigram indexes on venue and menu-item names

Revision ID: 229d06409d72
Revises:
Create Date: 2026-07-30

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "229d06409d72"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
    op.execute("DROP EXTENSION IF EXISTS postgis")
