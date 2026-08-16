"""extensions

Creates the two Postgres extensions every later revision depends on:

- ``btree_gist`` — the ``bookings`` exclusion constraint mixes ``=`` on an int
  with ``&&`` on a range, which plain GiST cannot index
- ``pg_trgm``    — the GIN trigram indexes on venue and menu-item names

Both ship with PostgreSQL itself, so any stock server can run this schema.
``postgis`` was here too, for a ``geography`` column on ``venues``; it was the
one requirement a managed Postgres could not satisfy, and distance is now
computed from the plain ``latitude``/``longitude`` columns instead.

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
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
