"""drop subscriptions

Revision ID: c638b32427c8
Revises: 3845cb0ff4f9
Create Date: 2026-07-30 16:07:55.903778

"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c638b32427c8"
down_revision: str | Sequence[str] | None = "3845cb0ff4f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the subscriptions module.

    Order matters and autogenerate got it wrong: `subscription_plans` is the parent
    of both `user_subscriptions` and `subscription_plan_translations`, and
    `user_subscriptions` is in turn referenced by `payments` and
    `promo_code_redemptions`. Children go first, parent last.

    The CHECK constraint rewrites are hand-written — Alembic does not autogenerate
    constraint text changes, so nothing here would have been detected.
    """
    # `ck_payments_exactly_one_target` names the column that is about to be dropped,
    # so it has to go before the column does.
    op.drop_constraint("ck_payments_exactly_one_target", "payments", type_="check")
    op.drop_constraint("ck_payments_kind", "payments", type_="check")
    op.drop_constraint("ck_promo_codes_applies_to", "promo_codes", type_="check")

    # No subscription was ever sold — the tables are empty — but a deployment that
    # did sell one would silently lose the link, so fail loudly instead.
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM payments WHERE subscription_id IS NOT NULL) THEN "
        "RAISE EXCEPTION 'payments rows still reference a subscription'; "
        "END IF; END $$;"
    )

    op.drop_constraint(op.f("payments_subscription_id_fkey"), "payments", type_="foreignkey")
    op.drop_column("payments", "subscription_id")
    op.drop_constraint(
        op.f("promo_code_redemptions_subscription_id_fkey"),
        "promo_code_redemptions",
        type_="foreignkey",
    )
    op.drop_column("promo_code_redemptions", "subscription_id")

    op.drop_table("subscription_plan_translations")
    op.drop_index(op.f("ix_user_subscriptions_user_id"), table_name="user_subscriptions")
    op.drop_table("user_subscriptions")
    op.drop_table("subscription_plans")

    # Recreated without the subscription arm. `booking_id` stays nullable: the
    # constraint is what enforces the rule, and a NOT NULL would have to be rewritten
    # again if a second payment target ever appears.
    op.create_check_constraint(
        "ck_payments_exactly_one_target", "payments", "booking_id IS NOT NULL"
    )
    op.create_check_constraint(
        "ck_payments_kind", "payments", "kind IN ('deposit', 'balance', 'full')"
    )
    op.create_check_constraint(
        "ck_promo_codes_applies_to", "promo_codes", "applies_to IN ('booking', 'both')"
    )


def downgrade() -> None:
    """Recreate the subscriptions module.

    Reverse order of `upgrade`: parents before children, and the tables before the
    columns whose foreign keys point at them. Autogenerate emitted these in the
    order it dropped them, which fails on the first foreign key.
    """
    op.drop_constraint("ck_payments_exactly_one_target", "payments", type_="check")
    op.drop_constraint("ck_payments_kind", "payments", type_="check")
    op.drop_constraint("ck_promo_codes_applies_to", "promo_codes", type_="check")

    op.create_table(
        "subscription_plans",
        sa.Column("code", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("price", sa.NUMERIC(precision=14, scale=2), autoincrement=False, nullable=False),
        sa.Column("currency", sa.VARCHAR(length=3), autoincrement=False, nullable=False),
        sa.Column("duration_days", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column(
            "benefit_percent", sa.NUMERIC(precision=5, scale=2), autoincrement=False, nullable=False
        ),
        sa.Column("is_active", sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column("sort_order", sa.INTEGER(), autoincrement=False, nullable=False),
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
            "code::text = ANY (ARRAY['monthly'::character varying, 'yearly'::character varying]::text[])",
            name=op.f("ck_subscription_plans_code"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("subscription_plans_pkey")),
        sa.UniqueConstraint(
            "code",
            name=op.f("subscription_plans_code_key"),
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
    )
    op.create_table(
        "user_subscriptions",
        sa.Column("user_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("plan_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("status", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("started_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column(
            "current_period_start", postgresql.TIMESTAMP(), autoincrement=False, nullable=False
        ),
        sa.Column(
            "current_period_end", postgresql.TIMESTAMP(), autoincrement=False, nullable=False
        ),
        sa.Column("next_payment_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column("auto_renew", sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column("cancelled_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
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
            "status::text = ANY (ARRAY['active'::character varying, 'past_due'::character varying, 'cancelled'::character varying, 'expired'::character varying]::text[])",
            name=op.f("ck_user_subscriptions_status"),
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["subscription_plans.id"], name=op.f("user_subscriptions_plan_id_fkey")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("user_subscriptions_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("user_subscriptions_pkey")),
    )
    op.create_index(
        op.f("ix_user_subscriptions_user_id"), "user_subscriptions", ["user_id"], unique=False
    )
    op.create_table(
        "subscription_plan_translations",
        sa.Column("plan_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("language_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("name", sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column("description", sa.TEXT(), autoincrement=False, nullable=True),
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
        sa.ForeignKeyConstraint(
            ["language_id"],
            ["languages.id"],
            name=op.f("subscription_plan_translations_language_id_fkey"),
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["subscription_plans.id"],
            name=op.f("subscription_plan_translations_plan_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("subscription_plan_translations_pkey")),
        sa.UniqueConstraint(
            "plan_id",
            "language_id",
            name=op.f("subscription_plan_translations_plan_id_language_id_key"),
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
    )

    op.add_column(
        "payments", sa.Column("subscription_id", sa.INTEGER(), autoincrement=False, nullable=True)
    )
    op.create_foreign_key(
        op.f("payments_subscription_id_fkey"),
        "payments",
        "user_subscriptions",
        ["subscription_id"],
        ["id"],
    )
    op.add_column(
        "promo_code_redemptions",
        sa.Column("subscription_id", sa.INTEGER(), autoincrement=False, nullable=True),
    )
    op.create_foreign_key(
        op.f("promo_code_redemptions_subscription_id_fkey"),
        "promo_code_redemptions",
        "user_subscriptions",
        ["subscription_id"],
        ["id"],
    )

    op.create_check_constraint(
        "ck_payments_exactly_one_target",
        "payments",
        "(booking_id IS NOT NULL)::int + (subscription_id IS NOT NULL)::int = 1",
    )
    op.create_check_constraint(
        "ck_payments_kind",
        "payments",
        "kind IN ('deposit', 'balance', 'full', 'subscription')",
    )
    op.create_check_constraint(
        "ck_promo_codes_applies_to",
        "promo_codes",
        "applies_to IN ('booking', 'subscription', 'both')",
    )
