import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.core.database.models_registry  # noqa: F401  (populates Base.metadata — import first)
from app.core.config import settings
from app.core.database.base import Base

config = context.config

# The URL comes from settings, never from alembic.ini.
config.set_main_option("sqlalchemy.url", str(settings.database.url))

if config.config_file_name is not None:
    # `disable_existing_loggers=False` is not cosmetic. The default is True, which
    # sets `disabled = True` on every logger that already exists and is not named in
    # alembic.ini — i.e. every `app.*` logger. Harmless from the CLI, where nothing
    # has logged yet, but the test suite imports the app and then runs migrations
    # in-process, so the default silently mutes application logging for the rest of
    # the session. Any test asserting on a log line would then pass vacuously,
    # including the ones that check a one-time code is *not* logged.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# app.core.database.models_registry is imported above, so every table is registered.
target_metadata = Base.metadata

# Filled from `pg_depend` at connection time. `--sql` mode has no connection to
# ask, so there it stays empty — the extensions this schema uses (btree_gist,
# pg_trgm) create no tables, so there is nothing to filter offline.
_extension_owned_tables: frozenset[str] = frozenset()

EXTENSION_OWNED_TABLES_SQL = """
SELECT c.relname
FROM pg_class c
JOIN pg_depend d ON d.objid = c.oid AND d.deptype = 'e'
JOIN pg_extension e ON e.oid = d.refobjid
WHERE c.relkind IN ('r', 'v', 'm', 'p', 'f')
"""


def include_object(
    obj: Any,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: Any,
) -> bool:
    """Restrict autogenerate to a named subset of tables.

    Used as `alembic revision --autogenerate -x only=table_a,table_b`, which is how
    one revision per module was produced from a single metadata. Without the
    argument nothing is filtered, so ordinary autogenerate still sees everything.
    """
    # Anything an extension created. Such tables land on the connection's
    # search_path and reflect as ordinary default-schema tables our metadata has
    # never heard of — and autogenerate then proposes dropping every one.
    #
    # Filtering by `pg_depend` rather than by a hardcoded name list means enabling
    # another extension later needs no change here.
    if type_ == "table" and name in _extension_owned_tables:
        return False

    only = context.get_x_argument(as_dictionary=True).get("only")
    if not only:
        return True

    allowed = {t.strip() for t in only.split(",") if t.strip()}
    if type_ == "table":
        return name in allowed

    parent = getattr(obj, "table", None)
    return parent.name in allowed if parent is not None else True


def run_migrations_offline() -> None:
    """Run migrations without a DBAPI connection, emitting SQL to stdout."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    global _extension_owned_tables
    _extension_owned_tables = frozenset(
        row[0] for row in connection.execute(text(EXTENSION_OWNED_TABLES_SQL))
    )
    # The probe is a plain SELECT, but executing it opened an implicit transaction
    # that Alembic does not own — leaving it open makes `context.begin_transaction`
    # a no-op and the migration silently rolls back. Rolling back a read is free.
    connection.rollback()

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run the migrations over a sync-bridged connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
