"""The registry is the single point that makes models visible to Alembic.

A model that is not imported here is invisible to `--autogenerate`, which then
emits an empty revision and the table silently never gets created.
"""

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import models_registry
from app.core.database.base import Base

MODELS_ROOT = Path(__file__).resolve().parent.parent / "app" / "modules"


def test_registry_covers_every_model_file() -> None:
    model_files = sorted(p for p in MODELS_ROOT.glob("*/models/*.py") if p.name != "__init__.py")

    # 62 before the `payments` (3) and `promotions` (4) modules were dropped.
    # 55 before `auth_identity` was dropped with the Google sign-in surface.
    # 54 before `venue_type` and `venue_venue_type` were replaced by a column
    # on `venues` (2026-08-10).
    assert len(model_files) == 52
    assert len(Base.metadata.tables) == 52
    assert len(models_registry.__all__) == 52


def test_no_model_imports_another_modules_model() -> None:
    """Cross-module relationships use string targets — `ForeignKey("venues.id")`.

    Importing another module's model class is what causes circular imports at this
    table count, so it is checked rather than trusted.
    """
    offenders: list[str] = []
    for path in MODELS_ROOT.glob("*/models/*.py"):
        module = path.parent.parent.name
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            stripped = line.strip()
            if not stripped.startswith(("from app.modules.", "import app.modules.")):
                continue
            if f"app.modules.{module}." in stripped:
                continue
            offenders.append(f"{path.relative_to(MODELS_ROOT.parent.parent)}:{lineno} {stripped}")

    assert offenders == []


async def test_auth_identities_table_is_gone(session: AsyncSession) -> None:
    """The last provider left with Google, so the table has nothing to hold."""
    exists = await session.scalar(text("SELECT to_regclass('public.auth_identities') IS NOT NULL"))
    assert exists is False


async def test_venue_type_tables_are_gone(session: AsyncSession) -> None:
    """Two values do not need two tables."""
    for table in ("venue_types", "venue_venue_types"):
        exists = await session.scalar(text(f"SELECT to_regclass('public.{table}') IS NOT NULL"))
        assert exists is False, f"{table} still exists"


async def test_venue_carries_its_type_as_a_column(session: AsyncSession) -> None:
    column = await session.scalar(
        text("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'venues' AND column_name = 'venue_type'
        """)
    )
    assert column is not None
