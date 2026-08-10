"""name amenities in uzbek

Data-only revision. `amenities.name` currently holds the slug: the seed revision
inserted amenities without a translation row, so `73548a20054d` fell back to
`slug` when it collapsed `amenity_translations` into the column. `parking` is a
machine value that leaked into a user-facing label; this puts the Uzbek label
where the client reads it and leaves `slug` as the stable identifier.

Revision ID: fbf24d302b30
Revises: 944af78cfba8
Create Date: 2026-08-10 20:16:38.949699

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fbf24d302b30"
down_revision: str | Sequence[str] | None = "944af78cfba8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# slug -> Uzbek label
AMENITY_NAMES = [
    ("parking", "Avtoturargoh"),
    ("sound_system", "Ovoz tizimi"),
    ("stage", "Sahna"),
    ("air_conditioning", "Konditsioner"),
    ("professional_kitchen", "Professional oshxona"),
    ("wifi", "Wi-Fi"),
]


def _q(value: str) -> str:
    """Single-quote a literal for inline SQL."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def upgrade() -> None:
    """Upgrade schema."""
    for slug, name in AMENITY_NAMES:
        op.execute(f"UPDATE amenities SET name = {_q(name)} WHERE slug = {_q(slug)}")


def downgrade() -> None:
    """Downgrade schema."""
    slugs = ", ".join(_q(slug) for slug, _ in AMENITY_NAMES)
    op.execute(f"UPDATE amenities SET name = slug WHERE slug IN ({slugs})")
