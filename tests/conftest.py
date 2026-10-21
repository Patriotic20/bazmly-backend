"""Shared test fixtures.

Database-backed tests run against a real Postgres with the migrations applied.

No mocks and no SQLite: every interesting behaviour here — the booking exclusion
constraint, the partial unique indexes, `SELECT ... FOR UPDATE`, `DISTINCT ON`,
PostGIS distance, trigram search — is a Postgres feature that a fake would have to
reimplement, and a fake that reimplements them proves nothing about production.

Two session fixtures, because they answer different questions:

- `session` wraps the test in an outer transaction that is rolled back at
  teardown. Fast, isolated, and correct for anything single-connection. A
  constraint violation still fires here: Postgres checks unique indexes and
  exclusion constraints at statement time, not at commit.
- `committing_sessions` hands out two sessions on two real connections that
  really commit. Only these can show one caller winning a race against another,
  because a savepoint inside one transaction is invisible to a second connection.
  Cleanup is handled by `clean_domain_tables`.

The engine is function-scoped on purpose: asyncpg connections belong to the event
loop that created them, and pytest-asyncio gives each test its own loop.
"""

import os
from collections.abc import AsyncGenerator
from urllib.parse import urlparse, urlunparse

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.main import app

# tests/conftest.py -> tests/ -> repo root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Everything a test may write, in one CASCADE. The seeded reference data
# (staff_roles, permissions, service_catalog, amenities, and every
# region and district of Uzbekistan) is deliberately absent — factories depend on
# it and it is never mutated. `regions` and `districts` left this list when
# `944af78cfba8` turned them into reference data: truncating them would delete
# the seed for the rest of the session, and the rows the factories add on top
# carry random names and codes, so leaving them behind collides with nothing.
DOMAIN_TABLES = (
    "bookings",
    "orders",
    "menu_categories",
    "venue_tables",
    "venue_zones",
    "venues",
    "venue_groups",
    "users",
)


def _test_database_url() -> str:
    """`TEST_DATABASE_URL`, else the configured database with `_test` appended.

    Never the development database: this suite truncates tables.
    """
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    parsed = urlparse(str(settings.database.url))
    return urlunparse(parsed._replace(path=f"{parsed.path}_test"))


@pytest.fixture(scope="session")
def database_url() -> str:
    return _test_database_url()


@pytest.fixture(scope="session")
def _migrated(database_url: str) -> str:
    """Bring the test database to head once per session.

    `app/alembic/env.py` takes its URL from `settings` and ignores `alembic.ini`
    by design, so pointing the migration at the test database means pointing
    `settings` at it.
    """
    settings.database.url = database_url  # type: ignore[assignment]

    config = Config(os.path.join(PROJECT_ROOT, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(PROJECT_ROOT, "app", "alembic"))
    command.upgrade(config, "head")
    return database_url


@pytest.fixture
async def engine(_migrated: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(_migrated, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """A session inside an outer transaction that is always rolled back."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        db_session = factory()
        try:
            yield db_session
        finally:
            await db_session.close()
            await transaction.rollback()


@pytest.fixture
async def clean_domain_tables(engine: AsyncEngine) -> AsyncGenerator[None]:
    """Truncate everything a committing test may write, before and after.

    Before as well as after, so a test that dies mid-way cannot poison the next.
    """
    statement = text(f"TRUNCATE {', '.join(DOMAIN_TABLES)} RESTART IDENTITY CASCADE")
    async with engine.begin() as connection:
        await connection.execute(statement)
    yield
    async with engine.begin() as connection:
        await connection.execute(statement)


@pytest.fixture
async def committing_sessions(
    engine: AsyncEngine, clean_domain_tables: None
) -> AsyncGenerator[tuple[AsyncSession, AsyncSession]]:
    """Two sessions on two real connections, for genuine contention."""
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    first = factory()
    second = factory()
    try:
        yield first, second
    finally:
        await first.rollback()
        await second.rollback()
        await first.close()
        await second.close()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """An HTTP client bound directly to the ASGI app — no network, no database."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
