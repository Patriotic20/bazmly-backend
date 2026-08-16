"""identify a user by telegram

The app runs as a Telegram Mini App, where the user is already identified before
the first screen renders. Telegram hands over an account id and a name — no
phone number, no email — so `ck_users_phone_or_email` would have rejected every
one of them. It is rewritten to accept a Telegram id as the third way of being
identifiable rather than dropped: a row with none of the three is still a row
nobody can ever sign into.

`telegram_id` is BIGINT, not INTEGER. Telegram account ids passed 2^31 in 2021,
so the narrower column would reject new accounts while accepting old ones —
the kind of limit that looks like a random failure in production.

Alembic does not compare CHECK constraints, so that half is written by hand.

Revision ID: 5ce814a7d7a3
Revises: fbf24d302b30
Create Date: 2026-08-16 16:19:52.374472

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5ce814a7d7a3"
down_revision: str | Sequence[str] | None = "fbf24d302b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IDENTITY_CHECK = "ck_users_phone_or_email"
UNIQUE_TELEGRAM_ID = "uq_users_telegram_id"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
    op.create_unique_constraint(UNIQUE_TELEGRAM_ID, "users", ["telegram_id"])

    op.drop_constraint(IDENTITY_CHECK, "users", type_="check")
    op.create_check_constraint(
        IDENTITY_CHECK,
        "users",
        "phone IS NOT NULL OR email IS NOT NULL OR telegram_id IS NOT NULL",
    )


def downgrade() -> None:
    """Downgrade schema.

    Narrowing the check again would fail on any Telegram-only account, so those
    rows are deleted first. They cannot be preserved: without the column there is
    nothing left to identify them by, and the constraint is what says so.
    """
    op.execute(
        "DELETE FROM users WHERE phone IS NULL AND email IS NULL AND telegram_id IS NOT NULL"
    )

    op.drop_constraint(IDENTITY_CHECK, "users", type_="check")
    op.create_check_constraint(
        IDENTITY_CHECK,
        "users",
        "phone IS NOT NULL OR email IS NOT NULL",
    )

    op.drop_constraint(UNIQUE_TELEGRAM_ID, "users", type_="unique")
    op.drop_column("users", "telegram_id")
