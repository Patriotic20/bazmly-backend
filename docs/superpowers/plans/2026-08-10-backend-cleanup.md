# Backend Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the Swagger auth contract, remove Google authentication, collapse venue types to a two-value enum, give regions and districts admin CRUD plus full Uzbek reference data, and move the root `.md` files into `docs/`.

**Architecture:** Five phases in order. Phase 1 is documentation-only in effect. Phases 2, 3 and 4 each carry exactly one Alembic migration, run one phase at a time so every migration has a single unambiguous parent revision. Phase 5 is last so the earlier phases can append to `DECISIONS.md` in place before it moves.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic, Pydantic 2, PostgreSQL + PostGIS, pytest + pytest-asyncio, uv, ruff, mypy strict.

**Spec:** `docs/superpowers/specs/2026-08-10-backend-cleanup-design.md`

**Branch:** `backend-cleanup`, off `master` at `2836f37`.

**11 tasks:** Phase 1 → Task 1. Phase 2 → Tasks 2-4. Phase 3 → Tasks 5-6. Phase 4 →
Tasks 7-10. Phase 5 → Task 11.

## Global Constraints

- Python `>=3.14`. `except A, B:` without parentheses is valid here (PEP 758) — do not "fix" it.
- Run everything through uv: `uv run pytest` (see the override below), `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app`.
- **Always run the suite as `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest`.** The local `.env` sets `AUTH_MODE=disabled` with `DEV_USER_ID=3`; that user does not exist in the truncated test database, so `_dev_user` raises `AuthConfigurationError` and 34 tests fail for a reason that has nothing to do with your change. With the override: 122 passed, 0 failed, as of commit `e3895a2`. **That is the baseline — a task is green only at 122+ passing and 0 failing.** If you see exactly 34 failures naming `SECURITY__DEV_USER_ID=3 does not exist`, you forgot the override. Never "fix" those tests and never edit `.env`.
- ruff `line-length = 100`, lint set `E, F, I, N, UP, B, SIM, RUF`. mypy `strict = true`, excluding `app/alembic/versions/`.
- Tests run against a real PostgreSQL with migrations applied. No mocks for database behaviour, no SQLite. `TEST_DATABASE_URL`, else the configured database with `_test` appended.
- **Nothing in `app/core/dependencies.py` or in any service may raise `HTTPException`.** Failures are `DomainError` subclasses; `app/core/handlers.py` owns the status code.
- **All user-facing API strings are Uzbek** — error messages, `summary`, `description`. Code, identifiers, docstrings and commit messages stay English.
- Every route needs an explicit unique `operation_id`; `tests/api/test_contract.py` asserts this.
- **Never edit an existing Alembic revision.** Historical migrations are immutable, including their Google and `venue_types` references.
- **Each task ends on green tests and its own commit.** No commit may leave the
  application unrunnable — this is why Task 6 carries both its migration and its
  readers instead of splitting them.

## File Structure

**Phase 1**
- Modify: `app/core/dependencies.py` — swap three `Header()` params for one `HTTPBearer` scheme
- Modify: `tests/api/test_contract.py` — assert the OpenAPI security scheme exists

**Phase 2**
- Delete: `app/core/integrations/google/` (`__init__.py`, `verifier.py`), `tests/integrations/google/`
- Delete: `app/modules/auth/models/auth_identity.py`
- Modify: `app/modules/auth/api/v1/auth.py`, `services/auth_service.py`, `schemas/auth.py`, `schemas/__init__.py`, `models/__init__.py`, `enums.py`, `app/core/config.py`, `app/core/exceptions.py`, `app/core/handlers.py`, `app/main.py`, `app/core/database/models_registry.py`, `.env.template`
- Create: one Alembic revision dropping `auth_identities`

**Phase 3** (one task — migration and readers together)
- Create: `app/modules/venues/enums.py` — `VenueTypeSlug` + label map
- Delete: `app/modules/catalog/models/venue_type.py`, `app/modules/catalog/repositories/venue_type_repository.py`, `app/modules/venues/models/venue_venue_type.py`
- Modify: `app/modules/venues/models/venue.py`, `app/modules/venue_groups/models/venue_group.py`, `app/modules/venues/schemas/venue.py`, `repositories/venue_repository.py`, `services/venue_service.py`, `services/venue_onboarding_service.py`, `app/modules/catalog/api/v1/router.py`, `app/modules/catalog/services/catalog_service.py`, `tests/repositories/factories.py`
- Create: one Alembic revision — add columns, backfill, drop two tables

**Phase 4**
- Modify: `app/core/dependencies.py` — `PlatformRoleRequired`, `require_platform_role`, `AdminUser`
- Create: `app/modules/geo/services/region_service.py`, `services/district_service.py`, `app/modules/geo/api/v1/districts.py`
- Modify: `app/modules/geo/api/v1/router.py` (regions), `app/modules/geo/api/router.py`, `schemas/region.py`, `schemas/district.py`, `schemas/__init__.py`, `repositories/region_repository.py`, `repositories/district_repository.py`, `services/__init__.py`, `tests/conftest.py`, `tests/repositories/factories.py`
- Create: one Alembic revision — unique `regions.code`, then seed 14 regions and every district

**Phase 5**
- `git mv` seven root `.md` files into `docs/`; trim `README.md`; update every in-code reference

---

## Phase 1 — Bearer security scheme

### Task 1: Declare auth as an HTTPBearer scheme

**Files:**
- Modify: `app/core/dependencies.py:36` (`BEARER_PREFIX`), `:55-58` (`_bearer_token`), `:61-64`, `:114-117`, `:148-164`
- Test: `tests/api/test_contract.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `bearer_scheme: HTTPBearer` and `BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]` in `app/core/dependencies.py`. `CurrentUser`, `PendingUser`, `OptionalUser` keep their existing names and types.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_contract.py`:

```python
async def test_openapi_declares_a_bearer_security_scheme(client: AsyncClient) -> None:
    """The generated mobile client reads auth off `securitySchemes`.

    A raw `authorization` header param would instead surface as an optional string
    field, which reads as "this endpoint is public" and silently produces an SDK
    that never sends the token.
    """
    schema = (await client.get("/api/openapi.json")).json()

    schemes = schema["components"]["securitySchemes"]
    assert any(
        value.get("type") == "http" and value.get("scheme") == "bearer"
        for value in schemes.values()
    ), f"no HTTP bearer scheme in {sorted(schemes)}"


async def test_protected_route_references_the_scheme_not_a_header(client: AsyncClient) -> None:
    """`GET /api/v1/venue/groups` is owner-only and must document itself as such."""
    schema = (await client.get("/api/openapi.json")).json()
    operation = schema["paths"]["/api/v1/venue/groups"]["get"]

    assert operation.get("security"), "protected route declares no security requirement"
    parameter_names = {p["name"] for p in operation.get("parameters", [])}
    assert "authorization" not in parameter_names, (
        "auth is still a plain header parameter; Swagger will render a text box"
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/api/test_contract.py -k bearer_security_scheme -v`
Expected: FAIL — `KeyError: 'securitySchemes'`, since no security scheme is declared yet.

- [ ] **Step 3: Add the scheme and replace the header params**

In `app/core/dependencies.py`, add to the imports:

```python
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
```

Delete `BEARER_PREFIX` (line 36) and `_bearer_token` (lines 55-58), and put this in their place:

```python
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Kirish tokeni: `Authorization: Bearer <token>`",
)

BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]
"""The access token, or `None` when absent or not a bearer credential.

`auto_error=False` is load-bearing twice over. It keeps `get_current_user_optional`
able to return `None` instead of failing, and it keeps every rejection a
`DomainError` raised by us — `auto_error=True` would raise `HTTPException` from
inside the security scheme, which is exactly the HTTP vocabulary this module
keeps out of the domain.

FastAPI also returns `None` when the scheme is not `bearer`, which is the same
rule the hand-rolled prefix check enforced.
"""
```

Change the three signatures. `get_current_user`:

```python
async def get_current_user(
    session: SessionDep,
    credentials: BearerCredentials = None,
) -> UserRead:
```

and its token line:

```python
    token = credentials.credentials if credentials else None
    if token is None:
        raise AuthenticationRequiredError()
```

`get_current_user_pending_ok` takes the identical two changes.

`get_current_user_optional` — note the recursive call must now pass credentials, not a raw header:

```python
async def get_current_user_optional(
    session: SessionDep,
    credentials: BearerCredentials = None,
) -> UserRead | None:
    """For endpoints that personalise but do not require auth.

    A bad token is treated as no token: venue search must not start returning 401
    because someone's session quietly expired.
    """
    if auth_disabled():
        return await _dev_user(session)
    if credentials is None:
        return None
    try:
        return await get_current_user(session, credentials)
    except AuthenticationRequiredError, PermissionDeniedError:
        return None
```

Leave `Header` imported — `get_language_id` still uses it for `accept_language`.

- [ ] **Step 4: Run the new tests**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/api/test_contract.py -v`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Run the full suite — this touches every authenticated route**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest`
Expected: PASS. `tests/api/test_auth_mode_api.py` is the one that proves `AUTH_MODE=disabled` still resolves a user with no credential present.

- [ ] **Step 6: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy app`
Expected: clean.

- [ ] **Step 7: Confirm Swagger by eye**

Run: `uv run uvicorn app.main:app --reload` and open `http://127.0.0.1:8000/api/docs`.
Expected: one **Authorize** button top-right; `GET /api/v1/venue/groups` shows a padlock and no `authorization` text box.

- [ ] **Step 8: Commit**

```bash
git add app/core/dependencies.py tests/api/test_contract.py
git commit -m "Declare auth as an HTTPBearer scheme instead of a raw header"
```

---

## Phase 2 — Remove Google authentication

### Task 2: Pre-flight — count users who would lose access

**Files:** none. This task writes no code and produces a decision.

**Interfaces:**
- Consumes: nothing.
- Produces: a go/no-go for Task 4. Task 3 may proceed regardless.

> **ALREADY RUN — do not dispatch this task.** Executed by the controller against
> the development database on 2026-08-10, before Task 1:
>
> ```
> users total: 5
> auth_identities rows: 0
> users who would lose all access: 0
> ```
>
> The table is empty, so no account can be stranded and nothing needs a product
> decision. **The Task 4 gate is open.** The steps below are kept as the record of
> what was checked and as the procedure to repeat before this migration is applied
> to any other database — production above all, where the counts may differ.

- [ ] **Step 1: Count Google-only accounts**

```bash
uv run python - <<'PY'
import asyncio
from sqlalchemy import text
from app.core.database.db_helper import db_helper

async def main() -> None:
    async for session in db_helper.session_getter():
        total = await session.scalar(text("SELECT count(*) FROM auth_identities"))
        stranded = await session.scalar(text("""
            SELECT count(*) FROM users u
            JOIN auth_identities ai ON ai.user_id = u.id
            WHERE u.password_hash IS NULL
        """))
        print(f"auth_identities rows: {total}")
        print(f"users who would lose all access: {stranded}")
        break

asyncio.run(main())
PY
```

- [ ] **Step 2: Act on the count**

`0` → record it and continue to Task 3.

Anything above `0` → **stop and report the number to the user.** Those accounts have no password and no other credential; dropping the table locks them out permanently. The remedies (force a password reset, notify them first, migrate them to phone auth) are a product decision. Do not pick one. Complete Task 3 while waiting — it is reversible and touches no data — and hold Task 4.

- [ ] **Step 3: Commit the finding**

```bash
git commit --allow-empty -m "Record Google-only account count before dropping auth_identities

auth_identities rows: <N>
users with no password_hash: <N>"
```

### Task 3: Delete the Google code surface

**Files:**
- Delete: `app/core/integrations/google/__init__.py`, `app/core/integrations/google/verifier.py`, `tests/integrations/google/`
- Modify: `app/modules/auth/api/v1/auth.py:63-74`, `app/modules/auth/services/auth_service.py:158-197` and `:285-310`, `app/modules/auth/schemas/auth.py`, `app/modules/auth/schemas/__init__.py`, `app/core/config.py`, `app/core/exceptions.py`, `app/core/handlers.py`, `app/main.py`, `.env.template`
- Test: `tests/services/test_auth_service.py`, `tests/api/test_auth_api.py`

**Interfaces:**
- Consumes: nothing from Task 2.
- Produces: an auth module whose only credential paths are `register`, `login`, `staff_login`. `AuthService.google_login`, `_verify_google`, `_create_google_user_in_transaction`, the `GoogleLogin` schema and the `GoogleIdentity` dataclass no longer exist. `AuthIdentity` and `AuthProvider` still exist after this task — Task 4 removes them.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_auth_api.py`:

```python
async def test_google_login_route_is_gone(client: AsyncClient) -> None:
    """Google auth was removed; the route must not linger as a 500 or a stub."""
    response = await client.post("/api/v1/auth/social/google", json={"id_token": "anything"})
    assert response.status_code == 404


async def test_openapi_has_no_google_operation(client: AsyncClient) -> None:
    schema = (await client.get("/api/openapi.json")).json()
    assert not [path for path in schema["paths"] if "google" in path.lower()]
```

- [ ] **Step 2: Run to verify it fails**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/api/test_auth_api.py -k google -v`
Expected: FAIL — the route still answers (422 for the bad token, not 404).

- [ ] **Step 3: Delete the route and the service methods**

```bash
git rm -r app/core/integrations/google tests/integrations/google
```

From `app/modules/auth/api/v1/auth.py` remove the `@router.post("/social/google", ...)` block and its `google_login` handler, and drop `GoogleLogin` from the imports.

From `app/modules/auth/services/auth_service.py` remove `google_login`, `_verify_google`, `_create_google_user_in_transaction`, the `GoogleIdentity` import, and the `app.core.integrations.google` import. Leave `_default_language_id` and `_issue_tokens_in_transaction` — `register` and `login` both use them.

From `app/modules/auth/schemas/auth.py` remove the `GoogleLogin` model, and drop it from `app/modules/auth/schemas/__init__.py` including `__all__`.

- [ ] **Step 4: Strip the settings and the error type**

In `app/core/config.py` remove the Google client id / audience fields and any Google settings class, plus its attachment to the settings root. In `.env.template` remove the matching `APP_CONFIG__*GOOGLE*` lines.

In `app/core/exceptions.py` remove the Google-specific `DomainError` subclass; in `app/core/handlers.py` remove its handler registration and its import. In `app/main.py` remove any Google wiring.

- [ ] **Step 5: Verify nothing references Google outside migrations**

Run: `grep -rni google app/ tests/ .env.template README.md`
Expected: hits **only** under `app/alembic/versions/`. Those are immutable history — leave them. Any hit elsewhere is unfinished work in this task.

- [ ] **Step 6: Run the suite**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest`
Expected: PASS. Delete any test that only exercised the removed Google path; keep every phone-auth test untouched.

- [ ] **Step 7: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy app`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "Remove Google authentication endpoint, service and settings"
```

### Task 4: Drop auth_identities and AuthProvider

**Gate: OPEN.** Task 2 reported 0 `auth_identities` rows and 0 users who would lose
access. Proceed.

**Files:**
- Delete: `app/modules/auth/models/auth_identity.py`
- Modify: `app/modules/auth/models/__init__.py`, `app/modules/auth/enums.py`, `app/core/database/models_registry.py`
- Create: `app/alembic/versions/<generated>_drop_auth_identities.py`
- Test: `tests/test_models_registry.py`

**Interfaces:**
- Consumes: Task 2's count, Task 3's deletions.
- Produces: no `AuthIdentity`, no `AuthProvider`, no `auth_identities` table. `app/modules/auth/enums.py` exports `DevicePlatform, FriendshipStatus, UserRole, UserStatus, UserTheme` only.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_models_registry.py`:

```python
async def test_auth_identities_table_is_gone(session: AsyncSession) -> None:
    """The last provider left with Google, so the table has nothing to hold."""
    exists = await session.scalar(text("SELECT to_regclass('public.auth_identities') IS NOT NULL"))
    assert exists is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/test_models_registry.py -k auth_identities -v`
Expected: FAIL — the table is still present in the migrated test database.

- [ ] **Step 3: Remove the model and the enum**

```bash
git rm app/modules/auth/models/auth_identity.py
```

Drop `AuthIdentity` from `app/modules/auth/models/__init__.py` (import and `__all__`), drop the `AuthProvider` import and `__all__` entry from `app/modules/auth/enums.py`, and remove the model from `app/core/database/models_registry.py`.

Delete the `AuthIdentity` relationship from `app/modules/auth/models/user.py` if one is declared there — a `relationship()` pointing at a deleted class fails at mapper configuration, which surfaces as an error on the first query rather than at import.

- [ ] **Step 4: Generate the migration**

Run: `uv run alembic revision --autogenerate -m "drop auth identities"`

Then open the generated file and check it by hand. Autogenerate must have produced `op.drop_table("auth_identities")` and nothing else. Delete any unrelated diff it invented. The `downgrade()` recreates the table — including `provider`, `provider_user_id`, `user_id`, its FK and its unique constraint — but cannot restore rows; say so in a comment rather than leaving a silent data-loss hole.

- [ ] **Step 5: Apply and verify round-trip**

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```
Expected: all three succeed. A `downgrade` that errors is a broken migration even when `upgrade` works.

- [ ] **Step 6: Run the suite**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest`
Expected: PASS.

- [ ] **Step 7: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy app`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "Drop auth_identities table and the AuthProvider enum"
```

---

## Phase 3 — Venue types as a two-value enum

### Task 5: Add the VenueTypeSlug enum

**Files:**
- Create: `app/modules/venues/enums.py`, `tests/test_venue_type_enum.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `VenueTypeSlug(StrEnum)` with members `RESTORAN = "restoran"` and `TOYXONA = "toyxona"`; `VENUE_TYPE_LABELS: dict[VenueTypeSlug, str]`; `VENUE_TYPE_SORT_ORDER: dict[VenueTypeSlug, int]`. Tasks 6 and 7 import all three from `app.modules.venues.enums`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_venue_type_enum.py`:

```python
from app.modules.venues.enums import (
    VENUE_TYPE_LABELS,
    VENUE_TYPE_SORT_ORDER,
    VenueTypeSlug,
)


def test_exactly_two_venue_types() -> None:
    assert [member.value for member in VenueTypeSlug] == ["restoran", "toyxona"]


def test_every_member_has_an_uzbek_label_and_an_order() -> None:
    """The `/v1/venue-types` endpoint is gone, so these maps are the only source
    of the display name and the picker order."""
    for member in VenueTypeSlug:
        assert VENUE_TYPE_LABELS[member]
        assert VENUE_TYPE_SORT_ORDER[member] > 0

    orders = list(VENUE_TYPE_SORT_ORDER.values())
    assert len(set(orders)) == len(orders), "sort order must be a total order"


def test_restoran_sorts_before_toyxona() -> None:
    """The migration's backfill resolves a multi-typed venue by this order, so a
    change here silently changes what those venues become."""
    assert (
        VENUE_TYPE_SORT_ORDER[VenueTypeSlug.RESTORAN]
        < (VENUE_TYPE_SORT_ORDER[VenueTypeSlug.TOYXONA])
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/test_venue_type_enum.py -v`
Expected: FAIL — `ModuleNotFoundError: app.modules.venues.enums`.

- [ ] **Step 3: Write the enum**

Create `app/modules/venues/enums.py`:

```python
"""Enum values for the `venues` module.

`VenueTypeSlug` replaced a `venue_types` lookup table and a `venue_venue_types`
join. Two values that never change do not need a table, and the endpoint that
served them is gone — so the label and the order live here, next to the values
they describe, instead of in a row the client has to fetch first.
"""

from enum import StrEnum


class VenueTypeSlug(StrEnum):
    RESTORAN = "restoran"
    TOYXONA = "toyxona"


VENUE_TYPE_LABELS: dict[VenueTypeSlug, str] = {
    VenueTypeSlug.RESTORAN: "Restoran",
    VenueTypeSlug.TOYXONA: "To'yxona",
}

VENUE_TYPE_SORT_ORDER: dict[VenueTypeSlug, int] = {
    VenueTypeSlug.RESTORAN: 1,
    VenueTypeSlug.TOYXONA: 2,
}
```

- [ ] **Step 4: Run the test**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/test_venue_type_enum.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/modules/venues/enums.py tests/test_venue_type_enum.py
git commit -m "Add VenueTypeSlug enum with Uzbek labels and picker order"
```

### Task 6: Move venue type from tables to an enum column

Migration and readers land together. Split apart, the migration commit drops
`venue_types` while every reader still queries it — the suite goes red and the
application is unrunnable at that commit. One task, one working state.

This is the largest task in the plan. Work through the steps in order; the tests
only go green once the readers are rewritten at Step 9.

**Files:**
- Create: `app/alembic/versions/<generated>_venue_type_enum.py`
- Delete: `app/modules/venues/models/venue_venue_type.py`, `app/modules/catalog/models/venue_type.py`, `app/modules/catalog/repositories/venue_type_repository.py`
- Modify (models): `app/modules/venues/models/venue.py`, `app/modules/venue_groups/models/venue_group.py`, `app/modules/venues/models/__init__.py`, `app/modules/catalog/models/__init__.py`, `app/modules/catalog/repositories/__init__.py`, `app/core/database/models_registry.py`
- Modify (readers): `app/modules/venues/schemas/venue.py:143` and the create/update schemas, `app/modules/venues/repositories/venue_repository.py:76,192-195,324-344`, `app/modules/venues/services/venue_service.py:103-111`, `app/modules/venues/services/venue_onboarding_service.py:79,102,185`, `app/modules/catalog/api/v1/router.py:12-20`, `app/modules/catalog/services/catalog_service.py`, `tests/repositories/factories.py:51,94,97`
- Test: `tests/test_models_registry.py`, `tests/api/test_venue_search_api.py`, `tests/api/test_venue_onboarding_api.py`, `tests/repositories/test_venue_repository.py`

**Interfaces:**
- Consumes: `VenueTypeSlug`, `VENUE_TYPE_LABELS` from Task 5.
- Produces: `Venue.venue_type: Mapped[VenueTypeSlug]` (not null), `VenueGroup.primary_venue_type: Mapped[VenueTypeSlug]` (not null). `VenueType`, `VenueVenueType` and `VenueTypeRepository` no longer exist. Venue search takes `venue_type: VenueTypeSlug | None` instead of `venue_type_ids: list[int]`. `VenueDetailRead.venue_type: VenueTypeSlug` replaces `venue_types: list[VenueTypeRead]`. `factories.make_venue` takes `venue_type: VenueTypeSlug = VenueTypeSlug.RESTORAN`; `factories.get_venue_type` is deleted.

**Already measured — do not re-run these queries.** In the development database:
`kafe` 0 venues, `restoran` 2, `toyxona` 2; one venue group, primary type `toyxona`.
The `kafe` fold therefore rewrites nothing. Keep the fold in the migration anyway —
production may differ.

- [ ] **Step 1: Report the kafe count before changing anything**

```bash
uv run python - <<'PY'
import asyncio
from sqlalchemy import text
from app.core.database.db_helper import db_helper

async def main() -> None:
    async for session in db_helper.session_getter():
        rows = (await session.execute(text("""
            SELECT vt.slug, count(DISTINCT vvt.venue_id) AS venues
            FROM venue_types vt
            LEFT JOIN venue_venue_types vvt ON vvt.venue_type_id = vt.id
            GROUP BY vt.slug ORDER BY vt.slug
        """))).all()
        for slug, venues in rows:
            print(f"{slug}: {venues} venues")
        break

asyncio.run(main())
PY
```

Print the result into the commit message at Step 8. A non-trivial `kafe` count is worth telling the user about before it is folded into `restoran` — the fold is agreed, silence about its size is not.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_models_registry.py`:

```python
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
```

- [ ] **Step 3: Run to verify it fails**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/test_models_registry.py -k venue_type -v`
Expected: FAIL — both tables are present and the column is absent.

- [ ] **Step 4: Change the models**

In `app/modules/venues/models/venue.py`, next to `district_id`:

```python
    venue_type: Mapped[VenueTypeSlug] = mapped_column(
        Enum(VenueTypeSlug, name="venue_type_slug", native_enum=False, length=20),
        nullable=False,
        index=True,
    )
```

with `from sqlalchemy import Enum` and `from app.modules.venues.enums import VenueTypeSlug`.

`native_enum=False` stores a `VARCHAR` with a check constraint rather than a PostgreSQL `ENUM` type. Adding a value to a native enum needs `ALTER TYPE` and cannot be done inside a transaction on older servers; a check constraint is one `ALTER TABLE`. Match whichever convention the existing enum columns in this codebase already use — grep for `Enum(` under `app/modules/*/models/` first and follow it. Consistency beats this reasoning.

In `app/modules/venue_groups/models/venue_group.py`, replace `primary_venue_type_id` with the same column shape named `primary_venue_type`.

Then delete the dead classes:

```bash
git rm app/modules/venues/models/venue_venue_type.py \
       app/modules/catalog/models/venue_type.py \
       app/modules/catalog/repositories/venue_type_repository.py
```

and remove each from its package `__init__.py` (import **and** `__all__`) and from `app/core/database/models_registry.py`.

- [ ] **Step 5: Write the migration**

Run: `uv run alembic revision -m "venue type enum"` — **not** `--autogenerate`. Autogenerate emits add-column and drop-table with no backfill between them, which loses every venue's type.

Write `upgrade()` in this order — backfill strictly between add and drop:

```python
def upgrade() -> None:
    # 1. Nullable for now: there is nothing to put in it until the backfill runs.
    op.add_column("venues", sa.Column("venue_type", sa.String(length=20), nullable=True))
    op.add_column(
        "venue_groups",
        sa.Column("primary_venue_type", sa.String(length=20), nullable=True),
    )

    # 2. A venue with several types takes its lowest-sorted one, so `restoran`
    #    wins over `toyxona` and both win over `kafe`.
    op.execute("""
        UPDATE venues v SET venue_type = sub.slug
        FROM (
            SELECT DISTINCT ON (vvt.venue_id) vvt.venue_id, vt.slug
            FROM venue_venue_types vvt
            JOIN venue_types vt ON vt.id = vvt.venue_type_id
            ORDER BY vvt.venue_id, vt.sort_order
        ) AS sub
        WHERE sub.venue_id = v.id
    """)
    op.execute("""
        UPDATE venue_groups g SET primary_venue_type = vt.slug
        FROM venue_types vt
        WHERE vt.id = g.primary_venue_type_id
    """)

    # 3. `kafe` is not a value any more, and neither is a venue with no type row.
    op.execute(
        "UPDATE venues SET venue_type = 'restoran' WHERE venue_type IS DISTINCT FROM 'toyxona'"
    )
    op.execute(
        "UPDATE venue_groups SET primary_venue_type = 'restoran' "
        "WHERE primary_venue_type IS DISTINCT FROM 'toyxona'"
    )

    # 4. Now every row has a value, so the constraint can go on.
    op.alter_column("venues", "venue_type", nullable=False)
    op.alter_column("venue_groups", "primary_venue_type", nullable=False)
    op.create_check_constraint(
        "ck_venues_venue_type", "venues", "venue_type IN ('restoran', 'toyxona')"
    )
    op.create_check_constraint(
        "ck_venue_groups_primary_venue_type",
        "venue_groups",
        "primary_venue_type IN ('restoran', 'toyxona')",
    )
    op.create_index("ix_venues_venue_type", "venues", ["venue_type"])

    # 5. Only now is it safe to drop what we read from.
    op.drop_column("venue_groups", "primary_venue_type_id")
    op.drop_table("venue_venue_types")
    op.execute("DELETE FROM venue_type_translations")  # if the table exists
    op.drop_table("venue_types")
```

`downgrade()` recreates `venue_types` with the two rows, recreates `venue_venue_types`, repopulates both from the columns, restores `primary_venue_type_id`, then drops the columns. It cannot resurrect `kafe`; note that in a comment.

Before writing the `venue_type_translations` line, confirm the table's real name: `grep -rn "venue_type" app/alembic/versions/*_catalog.py`. Drop the line if no such table exists rather than guessing.

- [ ] **Step 6: Apply and verify round-trip**

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```
Expected: all three succeed.

- [ ] **Step 7: Check the model tests, and expect the readers to be red**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/test_models_registry.py -v`
Expected: PASS.

Then run the whole suite to see the work still ahead:
`APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest -q`
Expected: **failures** across venue search and onboarding — every reader still queries
the dropped tables. That is the state Steps 8-13 exist to fix. **Do not commit here.**
The single commit comes at Step 16, once the readers are green, so no commit in
history leaves the application unrunnable.

- [ ] **Step 8: Write the failing reader tests**

Append to `tests/api/test_venue_search_api.py`:

```python
async def test_search_filters_by_venue_type(client: AsyncClient, session: AsyncSession) -> None:
    restoran = await make_venue(session, venue_type=VenueTypeSlug.RESTORAN)
    await make_venue(session, venue_type=VenueTypeSlug.TOYXONA)

    response = await client.get("/api/v1/venues", params={"venue_type": "restoran"})

    assert response.status_code == 200
    returned = {item["id"] for item in response.json()["items"]}
    assert returned == {restoran.id}


async def test_search_rejects_an_unknown_venue_type(client: AsyncClient) -> None:
    """An unknown value is now a schema error, not a silent empty result — there
    is no lookup table left to miss."""
    response = await client.get("/api/v1/venues", params={"venue_type": "kafe"})
    assert response.status_code == 422


async def test_venue_types_endpoint_is_gone(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/venue-types")).status_code == 404
```

Confirm the real search path and its response envelope from the existing tests in the file before writing these — reuse whatever key that file already asserts on instead of assuming `items`.

- [ ] **Step 9: Run to verify they fail**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/api/test_venue_search_api.py -v`
Expected: FAIL.

- [ ] **Step 10: Update the factories first**

In `tests/repositories/factories.py` delete `get_venue_type`, and give `make_venue` and the group factory a `venue_type: VenueTypeSlug = VenueTypeSlug.RESTORAN` parameter that sets the new columns directly. Every other test file builds its fixtures through these, so this unblocks the whole suite at once.

- [ ] **Step 11: Update the read path**

`venue_repository.py`: drop the `VenueVenueType` import and the subquery at 192-195, replacing the filter with `stmt.where(Venue.venue_type == venue_type)` guarded by `if venue_type is not None`. Change the `venue_types: Sequence[VenueType]` field on the detail dataclass (line 76) to `venue_type: VenueTypeSlug`, and delete the separate types query at 324-344 — the value now arrives on the venue row itself, so that round-trip disappears.

`venue_service.py:103-111`: replace the list comprehension over `detail.venue_types` with the single value. If the response needs a display name, take it from `VENUE_TYPE_LABELS`.

`venue.py` schemas: `VenueDetailRead.venue_types: list[VenueTypeRead]` becomes `venue_type: VenueTypeSlug`; the create/update schemas take `venue_type: VenueTypeSlug` and `VenueTypeSlug | None` respectively; the search filter schema takes `venue_type: VenueTypeSlug | None = None`.

- [ ] **Step 12: Update onboarding and delete the catalog endpoint**

`venue_onboarding_service.py`: drop the `VenueTypeRepository` construction (line 79) and both `get_by_id` existence checks (102, 185). Pydantic rejects an invalid value before the service is reached, so those checks now only cost a query.

`app/modules/catalog/api/v1/router.py`: delete the `list_venue_types` route and its `VenueTypeRead` import. Remove the corresponding method from `catalog_service.py`, and delete `VenueTypeRead` from the catalog schemas if nothing else uses it — `grep -rn VenueTypeRead app/` before deleting.

- [ ] **Step 13: Run the full suite**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest`
Expected: PASS. Every venue-type reference in tests should now go through the enum.

- [ ] **Step 14: Confirm nothing references the old shape**

Run: `grep -rn "venue_type_id\|VenueVenueType\|VenueTypeRepository\|venue_types" app/ tests/`
Expected: hits only under `app/alembic/versions/`.

- [ ] **Step 15: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy app`
Expected: clean.

- [ ] **Step 16: Commit — one commit for the whole task**

```bash
git add -A
git commit -m "Replace the venue_types tables with a venue_type enum column

Backfilled from venue_venue_types by lowest sort_order before the drop, so a
multi-typed venue keeps restoran over toyxona. Readers move in the same commit:
search filters on the column, VenueDetailRead carries a single value, and
GET /v1/venue-types is gone. Splitting the migration from the readers would have
left one commit where the tables are dropped and every reader still queries them.

Venue counts by type before migration: <paste Step 1 output>"
```

---

## Phase 4 — Geo: admin CRUD and Uzbek reference data

### Task 7: Add a platform-admin guard

**Files:**
- Modify: `app/core/dependencies.py` (after `GroupPermissionRequired`, ~line 324)
- Test: `tests/api/test_permissions_api.py`

**Interfaces:**
- Consumes: `CurrentUser` from Task 1.
- Produces: `class PlatformRoleRequired` with a `.roles: frozenset[UserRole]` attribute, `require_platform_role(*roles: UserRole) -> params.Depends`, and `AdminUser = Annotated[UserRead, require_platform_role(UserRole.ADMIN, UserRole.MODERATOR)]`. Tasks 9 and 10 use `AdminUser`.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_permissions_api.py`:

```python
async def test_platform_role_guard_rejects_a_customer(session: AsyncSession) -> None:
    """Platform role is a different axis from staff permissions: an admin of one
    venue group must not thereby be an admin of the country's district list."""
    guard = PlatformRoleRequired(UserRole.ADMIN)
    customer = await make_user(session, role=UserRole.CUSTOMER)

    with pytest.raises(PermissionDeniedError):
        await guard(user=UserRead.model_validate(customer))


async def test_platform_role_guard_accepts_an_admin(session: AsyncSession) -> None:
    guard = PlatformRoleRequired(UserRole.ADMIN)
    admin = await make_user(session, role=UserRole.ADMIN)

    assert (await guard(user=UserRead.model_validate(admin))).id == admin.id
```

Check `tests/repositories/factories.py` for the real user factory name and whether it accepts `role`; add the parameter if it does not.

- [ ] **Step 2: Run to verify it fails**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/api/test_permissions_api.py -k platform_role -v`
Expected: FAIL — `ImportError: cannot import name 'PlatformRoleRequired'`.

- [ ] **Step 3: Write the guard**

Add to `app/core/dependencies.py`:

```python
class PlatformRoleRequired:
    """Guards a platform-wide write on the caller's own `users.role`.

    A different axis from `PermissionRequired`: that one asks what the caller may
    do inside one venue group, which is the wrong question for national reference
    data. A group owner holds `admin` *within their chain* and must not thereby be
    able to rename a viloyat.

    Reads nothing from the database — the role is already on the resolved
    `UserRead`, so this is one comparison and no query.

    A class rather than a closure so `.roles` stays readable from outside, the way
    `tests/api/test_contract.py` reads `.slug` off the staff guards.
    """

    def __init__(self, *roles: UserRole) -> None:
        self.roles = frozenset(roles)

    async def __call__(self, user: CurrentUser) -> UserRead:
        if auth_disabled():
            return user
        if user.role not in self.roles:
            raise PermissionDeniedError(
                "Bu amal uchun ruxsat yo'q",
                details={"required_roles": sorted(role.value for role in self.roles)},
            )
        return user


def require_platform_role(*roles: UserRole) -> params.Depends:
    """`Depends` around `PlatformRoleRequired`. See `require_permission`."""
    guard: params.Depends = Depends(PlatformRoleRequired(*roles))
    return guard


AdminUser = Annotated[UserRead, require_platform_role(UserRole.ADMIN, UserRole.MODERATOR)]
```

Add `UserRole` to the existing `from app.modules.auth.enums import UserStatus` import.

The `auth_disabled()` bypass matches every other guard in this file; without it `AUTH_MODE=disabled` would break the moment an admin route exists.

- [ ] **Step 4: Run the test**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/api/test_permissions_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/dependencies.py tests/api/test_permissions_api.py tests/repositories/factories.py
git commit -m "Add a platform-role guard for admin-only writes"
```

### Task 8: Region write API

**Files:**
- Create: `app/modules/geo/services/region_service.py`, `tests/api/test_geo_admin_api.py`
- Modify: `app/modules/geo/api/v1/router.py`, `app/modules/geo/schemas/region.py`, `app/modules/geo/schemas/__init__.py`, `app/modules/geo/repositories/region_repository.py`, `app/modules/geo/services/__init__.py`
- Create: an Alembic revision adding `uq_regions_code`

**Interfaces:**
- Consumes: `AdminUser` from Task 7.
- Produces: `RegionCreate(name: str, code: str)`, `RegionUpdate(name: str | None, code: str | None)`; `RegionService(session)` with `async create(payload) -> RegionRead`, `async update(region_id, payload) -> RegionRead`, `async delete(region_id) -> None`. Task 9 mirrors this shape for districts.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_geo_admin_api.py`:

```python
async def test_admin_creates_a_region(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v1/regions",
        json={"name": "Namangan", "code": "UZ-NG"},
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["code"] == "UZ-NG"


async def test_customer_cannot_create_a_region(
    client: AsyncClient, customer_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/regions",
        json={"name": "Namangan", "code": "UZ-NG"},
        headers=customer_headers,
    )
    assert response.status_code == 403


async def test_listing_regions_needs_no_auth(client: AsyncClient) -> None:
    """Customers pick a region before they ever sign in."""
    assert (await client.get("/api/v1/regions")).status_code == 200


async def test_duplicate_region_code_is_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    body = {"name": "Namangan", "code": "UZ-NG"}
    assert (
        await client.post("/api/v1/regions", json=body, headers=admin_headers)
    ).status_code == 201

    second = await client.post(
        "/api/v1/regions", json={"name": "Boshqa", "code": "UZ-NG"}, headers=admin_headers
    )
    assert second.status_code == 422


async def test_deleting_a_region_with_districts_is_refused(
    client: AsyncClient, session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    """A raw FK violation would surface as a 500; this must be a validation error."""
    district = await make_district(session)

    response = await client.delete(f"/api/v1/regions/{district.region_id}", headers=admin_headers)

    assert response.status_code == 422
```

Add `admin_headers` and `customer_headers` fixtures to `tests/api/conftest.py`: create a user with that role and mint a real access token via `app.core.security`, following whatever `tests/api/test_auth_api.py` already does to authenticate.

- [ ] **Step 2: Run to verify they fail**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/api/test_geo_admin_api.py -v`
Expected: FAIL — 405 on POST, since only GET routes exist.

- [ ] **Step 3: Add the unique constraint migration**

`regions.code` is `nullable=False` but not unique today, so duplicates may already exist. Check first:

```bash
uv run python -c "
import asyncio
from sqlalchemy import text
from app.core.database.db_helper import db_helper
async def main():
    async for s in db_helper.session_getter():
        print((await s.execute(text('SELECT code, count(*) FROM regions GROUP BY code HAVING count(*) > 1'))).all())
        break
asyncio.run(main())"
```

Empty result → `uv run alembic revision -m "unique region code"` with `op.create_unique_constraint("uq_regions_code", "regions", ["code"])` and the matching `drop_constraint` in `downgrade()`. Non-empty → report the duplicates to the user; do not silently rename rows.

Add `unique=True` to `Region.code` in `app/modules/geo/models/region.py` so the model matches the database.

- [ ] **Step 4: Write the schemas**

In `app/modules/geo/schemas/region.py`:

```python
class RegionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=2, max_length=20, pattern=r"^UZ-[A-Z]{2}$")


class RegionUpdate(BaseModel):
    """Every field optional — PATCH, not PUT."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    code: str | None = Field(default=None, min_length=2, max_length=20, pattern=r"^UZ-[A-Z]{2}$")
```

Export both from `app/modules/geo/schemas/__init__.py`, `__all__` included.

- [ ] **Step 5: Write the service**

Create `app/modules/geo/services/region_service.py`. `LocationService` stays read-only and customer-facing; admin writes live here so one file does not own both.

```python
class RegionService:
    """Admin writes over `regions`. Reads stay in `LocationService`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.regions = RegionRepository(session)
        self.districts = DistrictRepository(session)

    async def create(self, payload: RegionCreate) -> RegionRead:
        if await self.regions.get_by_code(payload.code) is not None:
            raise ValidationFailedError("Bu kod allaqachon band", details={"code": payload.code})
        region = await self.regions.create(name=payload.name, code=payload.code)
        await self.session.commit()
        return RegionRead.model_validate(region)

    async def delete(self, region_id: int) -> None:
        region = await self.regions.get_by_id(region_id)
        if region is None:
            raise NotFoundError("Viloyat topilmadi")
        if await self.districts.count_for_region(region_id) > 0:
            raise ValidationFailedError(
                "Viloyatni o'chirish uchun avval uning tumanlarini o'chiring",
                details={"region_id": region_id},
            )
        await self.regions.delete(region)
        await self.session.commit()
```

`update` follows the same shape: load or `NotFoundError`, re-check `code` uniqueness when `code` changes, apply only the fields that were set (`payload.model_dump(exclude_unset=True)`), commit, return.

The uniqueness pre-check is for the message, not the guarantee — the constraint from Step 3 is the guarantee. Two concurrent creates can both pass the check; the second then fails at the database, which is correct.

Add `get_by_code`, `create`, `delete` to `RegionRepository` and `count_for_region` to `DistrictRepository`, following those files' existing method style. Export `RegionService` from `app/modules/geo/services/__init__.py`.

- [ ] **Step 6: Add the routes**

In `app/modules/geo/api/v1/router.py`, alongside the two existing GETs:

```python
@router.post(
    "",
    response_model=RegionRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="geo_create_region",
    summary="Viloyat qo'shish",
    description="Faqat administrator uchun.",
)
async def create_region(payload: RegionCreate, session: SessionDep, _: AdminUser) -> RegionRead:
    return await RegionService(session).create(payload)
```

`PATCH /{region_id}` and `DELETE /{region_id}` (204, returning `None`) follow the same three-line shape. Every `operation_id` is unique and every `summary`/`description` is Uzbek.

- [ ] **Step 7: Run the tests**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/api/test_geo_admin_api.py -v && APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest`
Expected: PASS.

- [ ] **Step 8: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy app`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "Add admin CRUD for regions"
```

### Task 9: District write API

**Files:**
- Create: `app/modules/geo/services/district_service.py`, `app/modules/geo/api/v1/districts.py`
- Modify: `app/modules/geo/api/router.py`, `app/modules/geo/schemas/district.py`, `app/modules/geo/schemas/__init__.py`, `app/modules/geo/repositories/district_repository.py`, `app/modules/geo/services/__init__.py`
- Test: `tests/api/test_geo_admin_api.py`

**Interfaces:**
- Consumes: `AdminUser` (Task 7), `RegionService`'s conventions (Task 8).
- Produces: `DistrictCreate(region_id, name, latitude, longitude)`, `DistrictUpdate` with all four optional; `DistrictService(session)` with `create` / `update` / `delete`. Task 10's seed migration assumes these columns and nothing more.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_geo_admin_api.py`:

```python
async def test_admin_creates_a_district(
    client: AsyncClient, session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    region = await make_region(session)

    response = await client.post(
        "/api/v1/districts",
        json={
            "region_id": region.id,
            "name": "Chilonzor",
            "latitude": "41.275400",
            "longitude": "69.204200",
        },
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Chilonzor"


async def test_district_rejects_coordinates_outside_uzbekistan(
    client: AsyncClient, session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    """Catches a transposed lat/lng at the edge: 69,41 is in China, 41,69 is Tashkent."""
    region = await make_region(session)

    response = await client.post(
        "/api/v1/districts",
        json={
            "region_id": region.id,
            "name": "Teskari",
            "latitude": "69.204200",
            "longitude": "41.275400",
        },
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_district_rejects_an_unknown_region(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/districts",
        json={
            "region_id": 10_000_000,
            "name": "Yo'q",
            "latitude": "41.300000",
            "longitude": "69.200000",
        },
        headers=admin_headers,
    )
    assert response.status_code in (404, 422)


async def test_deleting_a_district_used_by_a_venue_is_refused(
    client: AsyncClient, session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    venue = await make_venue(session)

    response = await client.delete(f"/api/v1/districts/{venue.district_id}", headers=admin_headers)

    assert response.status_code == 422


async def test_customer_cannot_delete_a_district(
    client: AsyncClient, session: AsyncSession, customer_headers: dict[str, str]
) -> None:
    district = await make_district(session)

    response = await client.delete(f"/api/v1/districts/{district.id}", headers=customer_headers)
    assert response.status_code == 403
```

Add a `make_region` factory if `factories.py` has none — `make_district` currently builds its region inline.

- [ ] **Step 2: Run to verify they fail**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/api/test_geo_admin_api.py -k district -v`
Expected: FAIL — 404, no `/api/v1/districts` router exists.

- [ ] **Step 3: Write the schemas with a coordinate envelope**

In `app/modules/geo/schemas/district.py`:

```python
# Uzbekistan's bounding box, rounded outward by a degree. Narrow enough to catch a
# transposed lat/lng — the country spans 37-46 N and 55-74 E, so a swapped pair
# lands outside on both axes.
MIN_LATITUDE, MAX_LATITUDE = Decimal("36"), Decimal("46")
MIN_LONGITUDE, MAX_LONGITUDE = Decimal("55"), Decimal("74")


class DistrictCreate(BaseModel):
    region_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=100)
    latitude: Decimal = Field(ge=MIN_LATITUDE, le=MAX_LATITUDE)
    longitude: Decimal = Field(ge=MIN_LONGITUDE, le=MAX_LONGITUDE)


class DistrictUpdate(BaseModel):
    region_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    latitude: Decimal | None = Field(default=None, ge=MIN_LATITUDE, le=MAX_LATITUDE)
    longitude: Decimal | None = Field(default=None, ge=MIN_LONGITUDE, le=MAX_LONGITUDE)
```

Both coordinates are required on create because `District.latitude`/`longitude` are `nullable=False`.

- [ ] **Step 4: Write the service**

Create `app/modules/geo/services/district_service.py` mirroring `RegionService`. Specifics:

- `create` and `update` verify the region exists via `RegionRepository.get_by_id`, raising `NotFoundError("Viloyat topilmadi")` when it does not.
- `delete` loads the district (`NotFoundError("Tuman topilmadi")`), then refuses while anything references it:

```python
        if await self.districts.count_references(district_id) > 0:
            raise ValidationFailedError(
                "Bu tuman ishlatilmoqda, uni o'chirish mumkin emas",
                details={"district_id": district_id},
            )
```

`count_references` counts `venues` **and** `user_recent_locations` for the district in one query — both carry a `district_id` FK, and checking only one leaves the other to fail as a 500.

- [ ] **Step 5: Add the router**

Districts need their own module because the v1 geo router is mounted at `prefix="/v1/regions"`. Create `app/modules/geo/api/v1/districts.py` with `router = APIRouter(prefix="/v1/districts", tags=["geo"])` and the three admin routes, each shaped like Task 8's. Include it from `app/modules/geo/api/router.py`.

The existing `GET /v1/regions/{region_id}/districts` stays where it is — it is a region-scoped read and moving it would break the mobile client.

- [ ] **Step 6: Run the tests**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/api/test_geo_admin_api.py -v && APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest`
Expected: PASS.

- [ ] **Step 7: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy app`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "Add admin CRUD for districts"
```

### Task 10: Seed Uzbekistan's regions and districts

**Files:**
- Create: `app/alembic/versions/<generated>_seed_uzbekistan_geo.py`
- Modify: `tests/conftest.py:50-62` (`DOMAIN_TABLES`), `tests/repositories/factories.py:61-73` (`make_district`)
- Test: `tests/test_geo_seed.py`

**Interfaces:**
- Consumes: `uq_regions_code` from Task 8.
- Produces: 14 seeded regions and every district, treated as reference data. `factories.make_district` returns a seeded district instead of creating one.

**The database is not empty, and this is the trap in this task.** Measured on
2026-08-10, the development database holds one hand-made region and one district:

```
regions:   (1, 'Toshkent shahri', 'TSH')
districts: (1, region_id=1, 'Chilonzor', 41.275000, 69.204000)
venues:    5 venues reference district 1
```

`TSH` is not the ISO code this task seeds (`UZ-TK`), so a plain
`ON CONFLICT (code) DO NOTHING` sees no conflict and inserts **a second Toshkent
shahri**. Chilonzor and its five venues stay attached to the old region while a
duplicate Chilonzor appears under the new one. Step 4a below reconciles this before
any insert; do not skip it, and do not solve it by deleting the existing rows —
five venues have a foreign key into that district.

- [ ] **Step 1: Build the dataset**

14 first-level units: Qoraqalpogʻiston Republic, Toshkent city, and the 12 viloyats (Andijon, Buxoro, Fargʻona, Jizzax, Namangan, Navoiy, Qashqadaryo, Samarqand, Sirdaryo, Surxondaryo, Toshkent, Xorazm). ISO 3166-2:UZ codes for `code`. Then every district and city under them — roughly 200 rows — each with `latitude` and `longitude`.

**These are real coordinates and this constraint is not negotiable:** source them from a public administrative-boundary dataset (OpenStreetMap `admin_level=6`, or GeoNames ADM2), not from recall. Uzbek names use the Latin orthography already in the codebase (`Toshkent`, `Qashqadaryo`, `Fargʻona`).

Any district whose coordinates cannot be sourced confidently goes into a list in the plan's completion report for the user to fill in. **Do not emit a plausible-looking number to close a gap** — a wrong centroid silently misplaces every venue in that district in distance search, and no test will catch it.

- [ ] **Step 2: Write the failing test**

Create `tests/test_geo_seed.py`:

```python
UZBEKISTAN_REGION_COUNT = 14


async def test_all_regions_are_seeded(session: AsyncSession) -> None:
    count = await session.scalar(text("SELECT count(*) FROM regions"))
    assert count == UZBEKISTAN_REGION_COUNT


async def test_every_region_has_districts(session: AsyncSession) -> None:
    orphans = (
        (
            await session.execute(
                text("""
        SELECT r.name FROM regions r
        LEFT JOIN districts d ON d.region_id = r.id
        WHERE d.id IS NULL
    """)
            )
        )
        .scalars()
        .all()
    )
    assert not orphans, f"regions with no districts: {orphans}"


async def test_every_district_sits_inside_uzbekistan(session: AsyncSession) -> None:
    """Catches a transposed or mistyped coordinate in the seed data itself."""
    outside = (
        await session.execute(
            text("""
        SELECT name, latitude, longitude FROM districts
        WHERE latitude NOT BETWEEN 36 AND 46 OR longitude NOT BETWEEN 55 AND 74
    """)
        )
    ).all()
    assert not outside, f"districts outside the country: {outside}"


async def test_region_codes_are_iso_3166_2(session: AsyncSession) -> None:
    bad = (
        (await session.execute(text("SELECT code FROM regions WHERE code !~ '^UZ-[A-Z]{2}$'")))
        .scalars()
        .all()
    )
    assert not bad, f"non-ISO region codes: {bad}"
```

- [ ] **Step 3: Run to verify it fails**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest tests/test_geo_seed.py -v`
Expected: FAIL — `regions` is empty, so the count is 0.

- [ ] **Step 4: Write the seed migration**

Run: `uv run alembic revision -m "seed uzbekistan geo"`.

Embed the rows as module-level constants in the revision file itself, following the style of `2026_07_30_1007-b7834c92fef5_seed_reference_data.py`. No external data file: a migration that reads a file changes meaning when that file is edited, and this one must mean the same thing forever.

```python
# (code, name)
REGIONS = [
    ("UZ-QR", "Qoraqalpogʻiston Respublikasi"),
    ("UZ-TK", "Toshkent shahri"),
    # ... 12 more
]

# region code -> [(name, latitude, longitude), ...]
DISTRICTS: dict[str, list[tuple[str, str, str]]] = {
    "UZ-TK": [
        ("Chilonzor", "41.2754", "69.2042"),
        # ...
    ],
    # ...
}
```

`upgrade()` opens with the reconciliation, before a single insert:

```python
def upgrade() -> None:
    # Pre-existing hand-made rows carry ad-hoc codes (`TSH` for Toshkent shahri) and
    # already have venues pointing at their districts. Renaming the code to ISO makes
    # the seed's ON CONFLICT recognise them, so the rows are adopted rather than
    # duplicated and every existing foreign key keeps resolving.
    op.execute("UPDATE regions SET code = 'UZ-TK' WHERE code = 'TSH'")
```

Extend that list if the pre-flight below finds other non-ISO codes. Then run the
check for anything still unmatched, and fail loudly rather than silently
duplicating:

```python
    # A non-ISO code left here would become a duplicate region below.
    op.execute("""
        DO $$
        DECLARE stray text;
        BEGIN
            SELECT string_agg(code, ', ') INTO stray
            FROM regions WHERE code !~ '^UZ-[A-Z]{2}$';
            IF stray IS NOT NULL THEN
                RAISE EXCEPTION 'non-ISO region codes present: %; reconcile them first', stray;
            END IF;
        END $$;
    """)
```

Then insert regions with `ON CONFLICT (code) DO NOTHING`, and districts resolved by
region code — `INSERT ... SELECT id FROM regions WHERE code = :code`, never a
hardcoded id, since ids are assigned by the sequence. Districts also need
`ON CONFLICT DO NOTHING` on `(region_id, name)`; add that unique constraint in this
migration if it does not exist, since it is what makes the adopted `Chilonzor` row
survive instead of gaining a twin. Coordinates go in as strings and cast to
`numeric(9,6)` so no float rounding sneaks in.

**Run this before writing the migration** and fold whatever it prints into the
reconciliation above — the development database is not the only one this will run
against:

```bash
uv run python -c "
import asyncio
from sqlalchemy import text
from app.core.database.db_helper import db_helper
async def main():
    async for s in db_helper.session_getter():
        print('non-ISO codes:', (await s.execute(text(
            \"SELECT id, name, code FROM regions WHERE code !~ '^UZ-[A-Z]{2}\$'\"))).all())
        print('districts:', (await s.execute(text(
            'SELECT d.id, d.name, r.code FROM districts d JOIN regions r ON r.id = d.region_id'))).all())
        break
asyncio.run(main())"
```

Make it idempotent with `ON CONFLICT (code) DO NOTHING` for regions, so a database that already holds some regions is not broken by re-running.

`downgrade()` deletes only the rows this migration inserted, matched on region code and district name. It must not `TRUNCATE` — by then real venues may point at these districts.

- [ ] **Step 5: Apply and verify round-trip**

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```
Expected: all three succeed.

- [ ] **Step 6: Reclassify regions and districts as reference data**

This is the step that is easy to miss and breaks the suite in a confusing way if skipped.

`tests/conftest.py` lists `"districts"` and `"regions"` in `DOMAIN_TABLES`, which is CASCADE-truncated between tests. Now that they are seeded reference data, truncating them destroys the seed for every later test — and CASCADE means it takes venues with it. Remove both entries and extend the comment above the tuple to say why they moved.

`factories.make_district` currently creates its own region and district. Change it to select a seeded district instead:

```python
async def make_district(session: AsyncSession) -> District:
    """A real seeded district — `districts` is reference data, not per-test fixture data."""
    district = await session.scalar(select(District).order_by(District.id).limit(1))
    assert district is not None, "run `alembic upgrade head`; geo seed data is missing"
    return district
```

- [ ] **Step 7: Run the full suite**

Run: `APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest`
Expected: PASS. Watch specifically for tests that assumed a per-test district — they now share one seeded row, so any test asserting on a district count needs updating.

- [ ] **Step 8: Lint and type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy app`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "Seed Uzbekistan's 14 regions and their districts

Coordinates sourced from <name the dataset>. Districts and regions are now
reference data and no longer truncated between tests.
Unsourced districts, if any: <list or 'none'>"
```

---

## Phase 5 — Docs reorganization

### Task 11: Move the root .md files into docs/

**Files:**
- `git mv`: `CONVENTIONS.md`, `DECISIONS.md`, `API_PLAN.md`, `MODEL_PLAN.md`, `REPOSITORY_PLAN.md`, `SCHEMA_PLAN.md`, `SERVICE_PLAN.md`
- Modify: `README.md`, plus every file that names one of the above
- Decide: `make_plan.md`

**Interfaces:**
- Consumes: the `DECISIONS.md` entries Phases 2-4 appended.
- Produces: a root holding only `README.md`; documentation under `docs/`.

- [ ] **Step 1: Find every reference before moving anything**

```bash
grep -rn "CONVENTIONS\.md\|DECISIONS\.md\|API_PLAN\.md\|MODEL_PLAN\.md\|REPOSITORY_PLAN\.md\|SCHEMA_PLAN\.md\|SERVICE_PLAN\.md\|make_plan\.md" \
  app/ tests/ docs/ README.md CLAUDE.md 2>/dev/null
```

Code docstrings cite these by name — `app/modules/auth/enums.py:6` says "See DECISIONS.md for why the declarations still sit in the models", and it is not the only one. Save the list; Step 5 fixes every hit.

- [ ] **Step 2: Read make_plan.md and decide**

Run: `cat make_plan.md` (128 lines).

If it is a scratch prompt rather than project documentation, propose deleting it and say why. If it documents something real, it moves to `docs/` with the rest. Either way, ask — do not move it blindly and do not delete it unilaterally.

- [ ] **Step 3: Move the files with history intact**

```bash
mkdir -p docs/architecture
git mv CONVENTIONS.md docs/conventions.md
git mv DECISIONS.md   docs/decisions.md
git mv API_PLAN.md        docs/architecture/api.md
git mv MODEL_PLAN.md      docs/architecture/model.md
git mv REPOSITORY_PLAN.md docs/architecture/repository.md
git mv SCHEMA_PLAN.md     docs/architecture/schema.md
git mv SERVICE_PLAN.md    docs/architecture/service.md
```

`git mv`, not `mv` plus `git add` — history should follow each file so `git log --follow` still works.

`docs/bazmly-db-schema.md` and `docs/db-schema-part2-venue-app.md` stay exactly where they are.

- [ ] **Step 4: Trim the moved files**

"Optimize" means two specific things:

1. Delete content the code now states more accurately — a plan file describing a module that exists is describing it twice, and the copy that cannot run is the one that goes stale.
2. Merge passages that repeat each other. The five architecture files total 784 lines and overlap heavily on the module layout and the service/repository split.

It does **not** mean rewriting decisions, dropping rationale, or removing a "why". `docs/decisions.md` is 1,161 lines and is where most of the win is: drop entries that a later entry superseded, and entries about code that no longer exists — including the `AuthProvider`-table rationale and the `venue_types` rows that Phases 2 and 3 deleted.

Add a one-paragraph header to each moved file saying what it covers, so `docs/architecture/` reads as a set rather than five orphans.

- [ ] **Step 5: Fix every reference from Step 1**

Update each hit to the new path. In code docstrings prefer the bare new name (`docs/decisions.md`) over a relative path that breaks depending on the reader's location.

Then verify nothing dangles:

```bash
grep -rn "DECISIONS\.md\|CONVENTIONS\.md\|_PLAN\.md" app/ tests/ docs/ README.md
```
Expected: no hits outside `docs/superpowers/`, which quotes the old names historically and should be left alone.

- [ ] **Step 6: Rewrite README.md as an index**

`README.md` stays in the root — GitHub renders it as the landing page. Trim its 139 lines to: what the project is, the stack table, how to run it, how to test it, and a **Documentation** section linking into `docs/`. Anything longer belongs in `docs/` behind a link.

- [ ] **Step 7: Verify the tree**

```bash
ls *.md                    # expect: README.md (and make_plan.md if kept)
APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest   # expect: PASS — nothing here touches code
uv run ruff check .        # expect: clean; docstring edits can break line-length
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "Move project documentation into docs/ and trim it

Five *_PLAN.md files become docs/architecture/, CONVENTIONS.md and DECISIONS.md
move down a level, README.md stays as the index. In-code references updated in
the same commit so no docstring points at a path that no longer exists."
```

---

## Self-Review

**Spec coverage.** Phase 1 → Task 1. Phase 2 → Tasks 2-4, including the blocking pre-flight. Phase 3 → Tasks 5-6, covering the enum, the label map, the `kafe` fold, the backfill order, and the deleted endpoint. Phase 4 → Tasks 7-10, covering the admin guard, both CRUD surfaces, the ISO code constraint, the delete guard, and the seed. Phase 5 → Task 11, covering the moves, the trim, the README, and the cross-references. The spec's "Region gets no coordinates" is honoured: no task adds a coordinate column to `regions`.

**Type consistency.** `VenueTypeSlug`, `VENUE_TYPE_LABELS`, `VENUE_TYPE_SORT_ORDER` are defined in Task 5 and used under those names in Task 6. `AdminUser` and `PlatformRoleRequired` are defined in Task 7 and used in Tasks 8 and 9. `BearerCredentials` is defined in Task 1 and used nowhere later, which is correct — it is internal to `dependencies.py`. `RegionCreate`/`RegionUpdate` and `DistrictCreate`/`DistrictUpdate` are each defined before use.

**Two things left open on purpose.** Task 2 stops for a user decision if any account would be stranded. Task 10 reports any district whose coordinates could not be sourced rather than inventing them. Both are stated in the spec's Risks section; neither is a placeholder.

**One judgment call to flag at execution.** Task 6 Step 4 says to match the codebase's existing `Enum(...)` convention rather than blindly taking `native_enum=False`. Grep first, follow what is there.
