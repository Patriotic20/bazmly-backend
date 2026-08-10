"""collapse translations to uzbek only

Revision ID: 73548a20054d
Revises: c638b32427c8
Create Date: 2026-07-30 16:35:15.394482

Hand-written. Autogenerate produced this in the wrong order — it dropped every
`*_translations` table *before* adding the columns that replace them, which would
have discarded the data, and it added the new columns `NOT NULL` to tables that
already have rows, which fails outright.

The order here is: add nullable -> copy the Uzbek text across -> backfill whatever
had no translation at all -> tighten to NOT NULL -> drop the old tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "73548a20054d"
down_revision: str | Sequence[str] | None = "c638b32427c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (parent, translation table, fk column, [(parent column, translation column), ...],
#  column to fall back on when a row has no translation at all)
MOVES: list[tuple[str, str, str, list[tuple[str, str]], str | None]] = [
    ("amenities", "amenity_translations", "amenity_id", [("name", "name")], "slug"),
    ("venue_types", "venue_type_translations", "venue_type_id", [("name", "name")], "slug"),
    ("menu_categories", "menu_category_translations", "menu_category_id", [("name", "name")], None),
    (
        "menu_items",
        "menu_item_translations",
        "menu_item_id",
        [("name", "name"), ("description", "description")],
        None,
    ),
    (
        "menu_item_variants",
        "menu_item_variant_translations",
        "variant_id",
        [("name", "name")],
        None,
    ),
    (
        "banners",
        "banner_translations",
        "banner_id",
        [("title", "title"), ("subtitle", "subtitle")],
        None,
    ),
    (
        "service_catalog",
        "service_catalog_translations",
        "service_catalog_id",
        [("name", "name")],
        "slug",
    ),
    ("staff_roles", "staff_role_translations", "staff_role_id", [("name", "name")], "slug"),
    (
        "venue_groups",
        "venue_group_translations",
        "venue_group_id",
        [("name", "name"), ("description", "description")],
        None,
    ),
    (
        "venues",
        "venue_translations",
        "venue_id",
        [("name", "name"), ("description", "description"), ("tagline", "tagline")],
        None,
    ),
    ("venue_zones", "venue_zone_translations", "zone_id", [("name", "name")], None),
]

# Every column added, with its type and whether it ends up NOT NULL.
COLUMNS: dict[str, list[tuple[str, sa.types.TypeEngine[object], bool]]] = {
    "amenities": [("name", sa.String(100), True)],
    "venue_types": [("name", sa.String(100), True)],
    "menu_categories": [("name", sa.String(255), True)],
    "menu_items": [("name", sa.String(255), True), ("description", sa.Text(), False)],
    "menu_item_variants": [("name", sa.String(100), True)],
    "banners": [("title", sa.String(255), True), ("subtitle", sa.String(255), False)],
    "service_catalog": [("name", sa.String(255), True)],
    "staff_roles": [("name", sa.String(100), True)],
    "venue_groups": [("name", sa.String(255), True), ("description", sa.Text(), False)],
    "venues": [
        ("name", sa.String(255), True),
        ("description", sa.Text(), False),
        ("tagline", sa.String(120), False),
    ],
    "venue_zones": [("name", sa.String(100), True)],
}


def upgrade() -> None:
    # 1. Nullable first — the tables already hold rows, so NOT NULL would fail here.
    for table, cols in COLUMNS.items():
        for name, type_, _ in cols:
            op.add_column(table, sa.Column(name, type_, nullable=True))

    # 2. Copy the text across. `DISTINCT ON` with a priority picks the Uzbek row and
    #    falls back to whatever else exists, so a record translated only into Russian
    #    still keeps its name rather than being blanked.
    for parent, trans, fk, pairs, _ in MOVES:
        sets = ", ".join(f"{p} = src.{t}" for p, t in pairs)
        cols = ", ".join(f"t.{t}" for _, t in pairs)
        op.execute(
            f"""
            UPDATE {parent} AS p SET {sets}
            FROM (
                SELECT DISTINCT ON (t.{fk}) t.{fk} AS ref, {cols}
                FROM {trans} AS t
                JOIN languages AS l ON l.id = t.language_id
                ORDER BY t.{fk}, CASE l.code WHEN 'uz' THEN 0 WHEN 'en' THEN 1 ELSE 2 END
            ) AS src
            WHERE p.id = src.ref
            """
        )

    # 3. Anything with no translation at all. `slug`/`code` is a poor display name but
    #    it is unique, human-readable and already there — better than an empty string
    #    that renders as a blank row in the app.
    for parent, _, _, pairs, fallback in MOVES:
        target = pairs[0][0]
        source = fallback or "''"
        op.execute(f"UPDATE {parent} SET {target} = {source} WHERE {target} IS NULL")

    # 4. Now the NOT NULLs can go on.
    for table, cols in COLUMNS.items():
        for name, type_, required in cols:
            if required:
                op.alter_column(table, name, existing_type=type_, nullable=False)

    # 5. Search indexes move to the new columns.
    op.create_index(
        "ix_venues_name_trgm",
        "venues",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_menu_items_name_trgm",
        "menu_items",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    # 6. Only now is it safe to drop the sources.
    for _, trans, _, _, _ in MOVES:
        op.drop_table(trans)


def downgrade() -> None:
    """Recreate the tables and move the text back, as one Uzbek row each.

    This is lossy in one direction only: translations into other languages were
    already gone when `upgrade` ran, so there is nothing to restore beyond Uzbek.
    """
    uz = "(SELECT id FROM languages WHERE code = 'uz' LIMIT 1)"

    for parent, trans, fk, pairs, _ in MOVES:
        cols = "".join(f"    sa.Column({t!r}, sa.String(500), nullable=True),\n" for _, t in pairs)
        op.create_table(
            trans,
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column(fk, sa.Integer(), nullable=False),
            sa.Column("language_id", sa.Integer(), nullable=False),
            *[sa.Column(t, sa.Text(), nullable=True) for _, t in pairs],
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("timezone('UTC'::text, now())"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("timezone('UTC'::text, now())"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint([fk], [f"{parent}.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["language_id"], ["languages.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(fk, "language_id"),
        )
        target_cols = ", ".join(t for _, t in pairs)
        source_cols = ", ".join(p for p, _ in pairs)
        op.execute(
            f"INSERT INTO {trans} ({fk}, language_id, {target_cols}) "
            f"SELECT id, {uz}, {source_cols} FROM {parent}"
        )

    op.drop_index("ix_menu_items_name_trgm", table_name="menu_items")
    op.drop_index("ix_venues_name_trgm", table_name="venues")

    for table, cols in COLUMNS.items():
        for name, _, _ in cols:
            op.drop_column(table, name)
