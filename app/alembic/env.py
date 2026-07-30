import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.core.database.models_registry  # noqa: F401  (populates Base.metadata — import first)
from app.core.config import settings
from app.core.database.base import Base

config = context.config

# The URL comes from settings, never from alembic.ini.
config.set_main_option("sqlalchemy.url", str(settings.database.url))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# app.core.database.models_registry is imported above, so every table is registered.
target_metadata = Base.metadata

POSTGIS_MANAGED_TABLES = frozenset(
    {
        "spatial_ref_sys",
        "geography_columns",
        "geometry_columns",
        "raster_columns",
        "raster_overviews",
    }
)


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
    # PostGIS creates these in `public` and owns them. They are not in our
    # metadata, so without this autogenerate proposes dropping them every run.
    if type_ == "table" and name in POSTGIS_MANAGED_TABLES:
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
