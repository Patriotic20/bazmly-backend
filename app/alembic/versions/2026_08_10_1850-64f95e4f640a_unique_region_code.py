"""unique region code

Revision ID: 64f95e4f640a
Revises: 6ee3f460f08b
Create Date: 2026-08-10 18:50:54.558416

Checked `regions` in development first: one row, `(id=1, name='Toshkent shahri',
code='TSH')`. No duplicates, so the constraint is safe to add outright — no
dedup pass needed.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "64f95e4f640a"
down_revision: str | Sequence[str] | None = "6ee3f460f08b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_regions_code", "regions", ["code"])


def downgrade() -> None:
    op.drop_constraint("uq_regions_code", "regions", type_="unique")
