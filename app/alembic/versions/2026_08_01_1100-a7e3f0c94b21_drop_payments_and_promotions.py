"""drop payments and promotions

Nothing charges a card and nothing hands out a code any more, so the seven tables
those two modules owned come out together. They have to come out together: the
promotions side reaches into bookings and the payments side reaches into
promotions' neighbour, and dropping either half alone leaves a dangling foreign
key.

Order matters and autogenerate got it wrong twice. It emitted the drops
alphabetically, which puts `payments` ahead of `refunds` and `promo_codes` ahead
of both `user_promo_codes` and `bookings.promo_code_id` — every one of those
fails on a still-live foreign key. It also never noticed
`promo_code_redemptions_booking_id_fkey`, because that constraint is created by
hand at the end of the bookings revision rather than inside a `create_table`.

`banner_translations` is deliberately absent: 73548a20054d already dropped it when
translations collapsed to Uzbek, and its downgrade recreates it from `banners`.
That is also why `banners` comes back here carrying `title` and `subtitle` — by
this point in the chain they are real columns on the table, and 73548a20054d's
downgrade drops them.

Bookings lose the discount slot outright, not just the promo reference: with no
code to redeem, nothing can write to `discount_amount` or to the `discount` arm of
`ck_booking_price_lines_type` ever again. Leaving the NOT NULL column behind would
break every insert, since the model no longer supplies it. Rows written back when
codes were still redeemable are a different matter — they are real history, and
narrowing the constraint around them aborts the migration — so they are deleted
first rather than assumed away.

`ck_payments_kind`, `ck_payments_exactly_one_target` and
`ck_promo_codes_applies_to` need no separate drop: c638b32427c8 rewrote their text
but they still live on the tables, and they go down with them.

Revision ID: a7e3f0c94b21
Revises: 9c1f4a7d2b30
Create Date: 2026-08-01 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7e3f0c94b21"
down_revision: str | Sequence[str] | None = "9c1f4a7d2b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the payments and promotions modules.

    Children before parents throughout. The one non-table item — the booking's
    promo reference — goes first, because it is what keeps `promo_codes` pinned.
    """
    # The FK has to go before the column it lives on, and both before `promo_codes`.
    op.drop_constraint(op.f("bookings_promo_code_id_fkey"), "bookings", type_="foreignkey")
    op.drop_column("bookings", "promo_code_id")

    # A booking has nothing left that could discount it, so the column and the price
    # line arm that fed it both go. Without this the model and the table disagree and
    # every insert fails the NOT NULL that no longer has anything to satisfy it.
    op.drop_column("bookings", "discount_amount")

    # Discount lines first: the narrowed constraint rejects them, and there is nowhere
    # to move them — a discount is not a rental, a catering item or a deposit.
    # `bookings.total_amount` is left as priced on purpose: it is the figure the
    # customer agreed to, and recomputing it from the surviving lines would quietly
    # raise the price of every booking that ever used a code.
    op.execute("DELETE FROM booking_price_lines WHERE line_type = 'discount'")
    op.drop_constraint("ck_booking_price_lines_type", "booking_price_lines", type_="check")
    op.create_check_constraint(
        "ck_booking_price_lines_type",
        "booking_price_lines",
        "line_type IN ('hall_rental', 'catering', 'service_logistics', 'deposit')",
    )

    # Redemptions point at promo_codes, users and bookings all three, so this table
    # is the last thing holding a reference into any of them.
    op.drop_table("promo_code_redemptions")

    op.drop_index("ix_user_promo_codes_user_id_status_expires_at", table_name="user_promo_codes")
    op.drop_table("user_promo_codes")

    op.drop_index(op.f("ix_refunds_payment_id"), table_name="refunds")
    op.drop_table("refunds")
    op.drop_index(op.f("ix_payments_user_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(op.f("ix_payment_cards_user_id"), table_name="payment_cards")
    op.drop_table("payment_cards")

    op.drop_table("promo_codes")
    op.drop_table("banners")


def downgrade() -> None:
    """Recreate the payments and promotions modules.

    Reverse order of `upgrade`: parents before children, and the tables before the
    columns whose foreign keys point at them. Structural only — every card, payment,
    refund, code, redemption and discount price line ever recorded was destroyed by
    `upgrade`, `bookings.promo_code_id` comes back NULL for every row and
    `discount_amount` comes back zero, whatever it once held.

    The CHECK texts here are the post-c638b32427c8 ones, without the subscription
    arm: restoring the original wording would resurrect a target that no longer has
    a table behind it.
    """
    op.create_table(
        "banners",
        sa.Column("image_url", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("target_type", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("target_id", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("target_url", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column("sort_order", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("starts_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column("ends_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column("is_active", sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("timezone('UTC'::text, now())"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("timezone('UTC'::text, now())"),
            autoincrement=False,
            nullable=False,
        ),
        # Appended by 73548a20054d, hence last; its own downgrade drops them again.
        sa.Column("title", sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column("subtitle", sa.VARCHAR(length=255), autoincrement=False, nullable=True),
        sa.CheckConstraint(
            "target_type IN ('venue', 'category', 'promo', 'url')",
            name=op.f("ck_banners_target_type"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("banners_pkey")),
    )
    op.create_table(
        "promo_codes",
        sa.Column("code", sa.VARCHAR(length=50), autoincrement=False, nullable=False),
        sa.Column("discount_type", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("value", sa.NUMERIC(precision=14, scale=2), autoincrement=False, nullable=False),
        sa.Column("applies_to", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column(
            "min_amount", sa.NUMERIC(precision=14, scale=2), autoincrement=False, nullable=True
        ),
        sa.Column(
            "max_discount", sa.NUMERIC(precision=14, scale=2), autoincrement=False, nullable=True
        ),
        sa.Column("usage_limit_total", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("usage_limit_per_user", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("used_count", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("valid_from", postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column("valid_to", postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column("is_active", sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("timezone('UTC'::text, now())"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("timezone('UTC'::text, now())"),
            autoincrement=False,
            nullable=False,
        ),
        sa.CheckConstraint(
            "applies_to IN ('booking', 'both')", name=op.f("ck_promo_codes_applies_to")
        ),
        sa.CheckConstraint(
            "discount_type IN ('percent', 'fixed')", name=op.f("ck_promo_codes_type")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("promo_codes_pkey")),
        sa.UniqueConstraint("code", name=op.f("promo_codes_code_key")),
    )
    op.create_table(
        "payment_cards",
        sa.Column("user_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("provider", sa.VARCHAR(length=50), autoincrement=False, nullable=False),
        sa.Column("provider_token", sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column("brand", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("last_four", sa.VARCHAR(length=4), autoincrement=False, nullable=False),
        sa.Column("holder_name", sa.VARCHAR(length=200), autoincrement=False, nullable=False),
        sa.Column("expiry_month", sa.SMALLINT(), autoincrement=False, nullable=False),
        sa.Column("expiry_year", sa.SMALLINT(), autoincrement=False, nullable=False),
        sa.Column("is_default", sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column("verified_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("timezone('UTC'::text, now())"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("timezone('UTC'::text, now())"),
            autoincrement=False,
            nullable=False,
        ),
        sa.CheckConstraint(
            "brand IN ('humo', 'uzcard', 'visa', 'mastercard')",
            name=op.f("ck_payment_cards_brand"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("payment_cards_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("payment_cards_pkey")),
    )
    op.create_index(op.f("ix_payment_cards_user_id"), "payment_cards", ["user_id"], unique=False)
    op.create_table(
        "payments",
        sa.Column("user_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("booking_id", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("card_id", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("provider", sa.VARCHAR(length=50), autoincrement=False, nullable=False),
        sa.Column(
            "provider_transaction_id", sa.VARCHAR(length=255), autoincrement=False, nullable=True
        ),
        sa.Column("kind", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("amount", sa.NUMERIC(precision=14, scale=2), autoincrement=False, nullable=False),
        sa.Column("currency", sa.VARCHAR(length=3), autoincrement=False, nullable=False),
        sa.Column("status", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("paid_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column("failed_reason", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("timezone('UTC'::text, now())"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("timezone('UTC'::text, now())"),
            autoincrement=False,
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('deposit', 'balance', 'full')", name=op.f("ck_payments_kind")),
        sa.CheckConstraint(
            "status IN ('created', 'pending', 'paid', 'failed', 'refunded')",
            name=op.f("ck_payments_status"),
        ),
        sa.CheckConstraint("booking_id IS NOT NULL", name=op.f("ck_payments_exactly_one_target")),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("payments_booking_id_fkey")
        ),
        sa.ForeignKeyConstraint(
            ["card_id"],
            ["payment_cards.id"],
            name=op.f("payments_card_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("payments_user_id_fkey")),
        sa.PrimaryKeyConstraint("id", name=op.f("payments_pkey")),
    )
    op.create_index(op.f("ix_payments_user_id"), "payments", ["user_id"], unique=False)
    op.create_table(
        "refunds",
        sa.Column("payment_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("amount", sa.NUMERIC(precision=14, scale=2), autoincrement=False, nullable=False),
        sa.Column("reason", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column("status", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("provider_refund_id", sa.VARCHAR(length=255), autoincrement=False, nullable=True),
        sa.Column("refunded_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("timezone('UTC'::text, now())"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("timezone('UTC'::text, now())"),
            autoincrement=False,
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('created', 'pending', 'succeeded', 'failed')",
            name=op.f("ck_refunds_status"),
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payments.id"], name=op.f("refunds_payment_id_fkey")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("refunds_pkey")),
    )
    op.create_index(op.f("ix_refunds_payment_id"), "refunds", ["payment_id"], unique=False)
    op.create_table(
        "user_promo_codes",
        sa.Column("user_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("promo_code_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("code", sa.VARCHAR(length=50), autoincrement=False, nullable=False),
        sa.Column("source", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("status", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("expires_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column("used_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("timezone('UTC'::text, now())"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("timezone('UTC'::text, now())"),
            autoincrement=False,
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('signup', 'campaign', 'compensation')",
            name=op.f("ck_user_promo_codes_source"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'used', 'expired')", name=op.f("ck_user_promo_codes_status")
        ),
        sa.ForeignKeyConstraint(
            ["promo_code_id"], ["promo_codes.id"], name=op.f("user_promo_codes_promo_code_id_fkey")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("user_promo_codes_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("user_promo_codes_pkey")),
    )
    op.create_index(
        "ix_user_promo_codes_user_id_status_expires_at",
        "user_promo_codes",
        ["user_id", "status", "expires_at"],
        unique=False,
    )
    op.create_table(
        "promo_code_redemptions",
        sa.Column("promo_code_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("user_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("booking_id", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column(
            "discount_amount",
            sa.NUMERIC(precision=14, scale=2),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("redeemed_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("timezone('UTC'::text, now())"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("timezone('UTC'::text, now())"),
            autoincrement=False,
            nullable=False,
        ),
        # Added out-of-band by ace0856d75f4 rather than by the promotions revision,
        # because `bookings` did not exist yet when the table was first created.
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("promo_code_redemptions_booking_id_fkey")
        ),
        sa.ForeignKeyConstraint(
            ["promo_code_id"],
            ["promo_codes.id"],
            name=op.f("promo_code_redemptions_promo_code_id_fkey"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("promo_code_redemptions_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("promo_code_redemptions_pkey")),
    )

    op.drop_constraint("ck_booking_price_lines_type", "booking_price_lines", type_="check")
    op.create_check_constraint(
        "ck_booking_price_lines_type",
        "booking_price_lines",
        "line_type IN ('hall_rental', 'catering', 'service_logistics', 'discount', 'deposit')",
    )
    # NOT NULL on a populated table needs something for the existing rows; the default
    # is dropped again straight after, because the column never carried one — the
    # zero is supplied by the model.
    op.add_column(
        "bookings",
        sa.Column(
            "discount_amount",
            sa.NUMERIC(precision=14, scale=2),
            server_default=sa.text("0"),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.alter_column("bookings", "discount_amount", server_default=None)

    op.add_column(
        "bookings", sa.Column("promo_code_id", sa.INTEGER(), autoincrement=False, nullable=True)
    )
    op.create_foreign_key(
        op.f("bookings_promo_code_id_fkey"),
        "bookings",
        "promo_codes",
        ["promo_code_id"],
        ["id"],
        ondelete="SET NULL",
    )
