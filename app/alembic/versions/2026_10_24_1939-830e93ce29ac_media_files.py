"""media files: uploaded images, kept in the database

Dish photos had a `photo_url` column and nowhere to upload to. The bytes live in
Postgres rather than on disk because the backend container runs as a non-root
user and is replaced on every deploy, so a file written beside the code would
not survive the next release; rows here do, and they ride along in `pg_dump`.

Revision ID: 830e93ce29ac
Revises: d3c1a7f5e820
Create Date: 2026-10-24 19:39:39.471022

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "830e93ce29ac"
down_revision: str | Sequence[str] | None = "d3c1a7f5e820"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "media_files",
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("media_files")
