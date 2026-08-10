"""drop sms and otp, apple identities, verification timestamps

Registration no longer sends anything. A person types a phone number, then their
name and an optional password, and the account exists — so the OTP table, the SMS
delivery log and the "verified at" timestamps have nothing left to record. Apple
sign-in went with them; Google is the only provider now, and it is verified
against Google's own JWKS rather than trusted from the request body.

Revision ID: 9c1f4a7d2b30
Revises: 4f2ba1c07d9e
Create Date: 2026-08-01 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9c1f4a7d2b30"
down_revision: str | Sequence[str] | None = "4f2ba1c07d9e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("ix_sms_messages_status_created_at", table_name="sms_messages")
    op.drop_index("ix_sms_messages_phone_created_at", table_name="sms_messages")
    op.drop_table("sms_messages")

    op.drop_index(
        "ix_verification_codes_destination_purpose_created_at", table_name="verification_codes"
    )
    op.drop_table("verification_codes")

    # Apple rows first: the tightened constraint would reject them, and there is
    # no way to migrate them — an Apple `sub` means nothing to Google.
    op.execute("DELETE FROM auth_identities WHERE provider = 'apple'")
    op.drop_constraint("ck_auth_identities_provider", "auth_identities", type_="check")
    op.create_check_constraint(
        "ck_auth_identities_provider", "auth_identities", "provider IN ('google')"
    )

    op.drop_column("users", "phone_verified_at")
    op.drop_column("users", "email_verified_at")

    op.drop_column("staff_invitations", "sms_sent_at")
    op.drop_column("staff_invitations", "sms_provider_id")


def downgrade() -> None:
    """Downgrade schema.

    Structural only. The dropped rows — every SMS ever logged, every outstanding
    verification code and every linked Apple account — are gone for good, and the
    restored timestamp columns come back NULL for everyone.
    """
    op.add_column(
        "staff_invitations",
        sa.Column("sms_provider_id", sa.String(length=255), nullable=True),
    )
    op.add_column("staff_invitations", sa.Column("sms_sent_at", sa.DateTime(), nullable=True))

    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("phone_verified_at", sa.DateTime(), nullable=True))

    op.drop_constraint("ck_auth_identities_provider", "auth_identities", type_="check")
    op.create_check_constraint(
        "ck_auth_identities_provider", "auth_identities", "provider IN ('apple', 'google')"
    )

    op.create_table(
        "verification_codes",
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("destination", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("attempts_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("request_ip", postgresql.INET(), nullable=True),
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
        sa.CheckConstraint("channel IN ('sms', 'email')", name="ck_verification_codes_channel"),
        sa.CheckConstraint(
            "purpose IN ('registration', 'login', 'phone_change', 'email_change', 'card_binding')",
            name="ck_verification_codes_purpose",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_verification_codes_destination_purpose_created_at",
        "verification_codes",
        ["destination", "purpose", "created_at"],
        unique=False,
    )

    op.create_table(
        "sms_messages",
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("template_key", sa.String(length=50), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("provider_request_id", sa.String(length=64), nullable=True),
        sa.Column("provider_message_id", sa.String(length=64), nullable=True),
        sa.Column("parts_count", sa.SmallInteger(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider_status_raw", sa.String(length=30), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("status_updated_at", sa.DateTime(), nullable=True),
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
        sa.CheckConstraint(
            "purpose IN ('otp', 'staff_invitation', 'notification')", name="ck_sms_messages_purpose"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'sent', 'delivered', 'partly_delivered', 'undelivered', "
            "'expired', 'rejected', 'failed', 'skipped')",
            name="ck_sms_messages_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_request_id"),
    )
    op.create_index(
        "ix_sms_messages_phone_created_at", "sms_messages", ["phone", "created_at"], unique=False
    )
    op.create_index(
        "ix_sms_messages_status_created_at", "sms_messages", ["status", "created_at"], unique=False
    )
