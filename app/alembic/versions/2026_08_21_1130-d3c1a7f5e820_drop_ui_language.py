"""drop the ui language table and the column that pointed at it

Content has been Uzbek-only since `73548a20054d` collapsed every
`*_translations` table into a plain column on its parent. `languages` outlived
that: `GET /v1/languages` kept offering uz, en and ru while every response came
back in Uzbek regardless — a promise the API had no way to keep. The interface
language is a client concern now, and the frontend had already shipped its own
list without ever calling the endpoint.

`users.language_id` goes with it. It was `NOT NULL`, so registration had to look
up the `uz` row first and raise "Asosiy til sozlanmagan" when it was missing —
a seeding problem could stop sign-up outright, for a preference nothing read.

The downgrade rebuilds the table, re-seeds the three rows and points every user
at `uz`. It cannot restore a per-person choice: after this revision there is
nowhere that choice was kept.

Revision ID: d3c1a7f5e820
Revises: 5ce814a7d7a3
Create Date: 2026-08-21 11:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3c1a7f5e820"
down_revision: str | Sequence[str] | None = "5ce814a7d7a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same three rows `b7834c92fef5` seeded, so a downgrade lands on the state the
# upgrade found rather than on an empty table the old code would reject.
LANGUAGES = [
    ("uz", "O'zbekcha", "Uzbek", 1),
    ("en", "English", "English", 2),
    ("ru", "Russian", "Russian", 3),
]


def upgrade() -> None:
    """Upgrade schema.

    The column first: dropping it takes its foreign key with it, which is what
    frees the table. Reversing the order would fail on a dependency.
    """
    op.drop_column("users", "language_id")
    op.drop_table("languages")


def downgrade() -> None:
    """Downgrade schema.

    Nullable -> backfill -> tighten, because `users` already has rows and adding
    a `NOT NULL` column to a populated table fails outright.
    """
    op.create_table(
        "languages",
        sa.Column("code", sa.String(length=5), nullable=False),
        sa.Column("name_native", sa.String(length=100), nullable=False),
        sa.Column("name_english", sa.String(length=100), nullable=False),
        sa.Column("flag_url", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("timezone('UTC', now())"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("timezone('UTC', now())"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    for code, native, english, sort_order in LANGUAGES:
        op.execute(
            "INSERT INTO languages (code, name_native, name_english, is_active, sort_order) "
            f"VALUES ('{code}', '{native.replace(chr(39), chr(39) * 2)}', '{english}', "
            f"true, {sort_order})"
        )

    op.add_column("users", sa.Column("language_id", sa.Integer(), nullable=True))
    op.execute("UPDATE users SET language_id = (SELECT id FROM languages WHERE code = 'uz')")
    op.alter_column("users", "language_id", nullable=False)
    # Unnamed, so Postgres picks `users_language_id_fkey` again — the name the
    # original `5eac583a1f5a` left behind.
    op.create_foreign_key(None, "users", "languages", ["language_id"], ["id"])
