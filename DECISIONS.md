# Decisions

Choices the specs did not pin down, plus the places where a spec's own
instructions conflicted with each other.

- [Part 5 — API layer](#part-5--api-layer)
- [Part 4 — schemas and services](#part-4--schemas-and-services)
- [Part 3 — repository layer](#part-3--repository-layer)
- [Part 2 — models and migrations](#part-2--models-and-migrations)
- [Part 1 — initial scaffold](#part-1--initial-scaffold)

---

# Part 5 — API layer

113 operations across 100 paths, one router per module, two audiences, JWT auth.
Models, repositories and schemas are untouched.

## Conflicts with the task spec, and how each was resolved

### Access tokens are minted at the API boundary, not by `AuthService`

The spec wants a JWT carrying `sub`, `jti` and `type: "access"`. `AuthService`
issues an opaque random string. Changing it would mean editing the service layer.

`AuthService` keeps what it genuinely owns — the refresh token's row, hash,
rotation and revocation. The access token has no row: it is a stateless bearer
credential, so producing it is a transport concern and
`app/modules/auth/api/tokens.py` mints it, discarding the service's placeholder.

### `AuthService.refresh` gained family revocation

The required test demands that reusing a revoked refresh token revokes the whole
family. The service only raised. Family revocation cannot be done from the API
layer — detecting reuse needs the token row, and the API may not reach a
repository — so four lines were added to `AuthService.refresh`, marked
`# TODO(service)`.

### Three services were added, two of them because none existed

`LanguageService` (localization) and `CatalogService` (catalog) had no service at
all, but `GET /v1/languages`, `GET /v1/venue-types`, `GET /v1/amenities` and the
`get_language_id` dependency all need one. Without them the endpoints would have
reached into repositories, breaking the layering rule that has a grep in the
checklist. Both are read-only pass-throughs, marked `# TODO(service)`.

### The error envelope is now flat

`{"code", "message", "details", "request_id"}` rather than
`{"error": {...}}`. The spec for this layer is explicit, and the mobile team
generates clients from the schema — one less level to unwrap at every call site.
`CONVENTIONS.md` and the health test were updated to match.

### `complete-profile` needs its own auth dependency

`get_current_user` rejects any status but `active`, and a freshly verified account
is `pending_profile`. That is a deadlock: you cannot set your name until you are
active, and you cannot become active without setting your name.
`get_current_user_pending_ok` accepts `pending_profile` and is used by exactly one
endpoint. Blocked and deleted accounts are still refused.

## Bug found in the services layer

### `VenueRead` / `VenueGroupRead` could never be built

Six call sites did `VenueRead.model_validate(orm_row).model_copy(update={"name": ""})`.
`name` is a resolved translation, not a column, so validation failed on a missing
required field before `model_copy` could supply it — every call raised
`ValidationError`. It broke ~10 routes: venue update, branch list, all onboarding
steps, and both venue-group reads.

Found by `test_permissions_api`. Fixed at all six sites with a `_venue_read` /
`_group_read` helper that supplies the name explicitly, each marked
`# TODO(service)`. The methods still cannot resolve a real translated name because
they take no `language_id`; callers that need one use `get_detail`.

## Design notes

### Two audiences, two route trees

`venues` and `bookings` split `v1/` into `customer.py` and `venue.py`; `orders`,
`staff`, `menu` and `analytics` are staff-only. No endpoint branches on role: a
staff booking list and a guest booking list have different payloads and different
filters, and a response shape that depends on the caller is something no generated
client can express.

### `require_permission` is a factory, checked by a test that walks the tree

It resolves the user, reads `venue_id` from the path or the query, and calls
`StaffService.require_permission_in_transaction`. Group-scoped roles satisfy
venue-scoped checks anywhere in their chain.

`test_contract.py` walks every route's `dependant` tree and asserts each mutating
verb under `/api/v1/venue/` carries the guard, because a staff write that forgets
one is not a visible bug — it works, for everyone. That test caught
`PATCH /v1/venue/groups/{group_id}` shipping unguarded.

The one documented exception is `POST /v1/venue/staff/invitations/accept`: the
caller is proving who they are with a temporary password precisely because they do
not have an employment row yet.

### Webhooks are outside the versioned envelope

Payme and Click each expect their own response shape, and a gateway that cannot
parse what it gets back retries forever. They live in `app/core/webhooks/` with
their own error handling, verify an HMAC over the raw body before touching the
database, and are idempotent on `provider_transaction_id`.

An unconfigured secret means the provider is **off**, not open — an empty secret
compared against an empty header would otherwise authenticate everyone.

### Enumerating routes

This FastAPI version includes sub-routers lazily, so `app.routes` holds
`_IncludedRouter` wrappers rather than endpoints. `tests/api/conftest.py` has a
`walk_routes` helper that flattens the tree; the contract tests need real
`APIRoute` objects to read `operation_id`, `response_model` and the dependant tree.

### Session override is the only test seam

`get_session` is the single place a session enters a request, so overriding that
one dependency puts every service in the app onto the test's rolled-back
transaction. Routing, dependency resolution and exception handling are all real.

## Routes specified but not built

No service method exists behind these, and a route that returns a lie is worse
than one absent from the schema. Each needs the service work named:

venue create and `PATCH /{id}/status`; venue photos; zone create; table-QR create;
`GET /venues/by-qr/{token}`; `GET /{venue_id}/guest-tiers`; booking
confirm/reject; `receipt.pdf`; `GET /bookings/history`; blocked-slot writes; order
item update/delete/status; menu category and item update/delete; item variants and
photo; staff invitation revoke and `PATCH /{staff_id}`; review get/update/delete
and staff reply; payment-card delete and verify; subscription subscribe/cancel.

## Verification

| Check | Result |
| --- | --- |
| `API_PLAN.md` exists and matches the generated routes | pass — table generated from `app.openapi()` |
| `grep -rn "try:" app/modules/*/api/` | pass — no matches |
| `grep -rn "HTTPException" app/modules/*/api/` | pass — no matches; none anywhere outside `handlers.py` |
| `grep -rn "select(\|session.execute" app/modules/*/api/` | pass — no matches |
| Every route has `response_model`, `operation_id`, `summary` | pass — 113/113, asserted in a test |
| All `operation_id` unique | pass — asserted over `app.routes` |
| Every staff write has `require_permission` | pass — asserted by walking the dependant tree |
| `/api/openapi.json` validates, no `Response ...` placeholders | pass — OpenAPI 3.1.0, 153 schemas, 0 placeholders |
| `mypy --strict` and `ruff` | pass — 468 files |
| All required tests pass | pass — 35 API tests, 97 total |
| Models, repositories and schemas unchanged | pass — services changed, itemised above |

---

# Part 4 — schemas and services

47 schema families, 28 services, 21 domain exceptions. Models and migrations are
untouched; repositories gained methods and nothing else.

## Conflicts with the task spec, and how each was resolved

### Enums stay declared in the models; `enums.py` re-exports them

The spec wants each enum declared once in `app/modules/<module>/enums.py`, with
models importing it. All 34 are declared inside model files, and this task may not
modify models.

`enums.py` re-exports instead. There is still exactly one declaration of each,
models and schemas share the same object (`UserRole is ModelRole` → `True`), and
no schema redeclares one — which is what the rule protects. Moving the class
bodies into `enums.py` later is mechanical.

### `uq_users_phone` does not exist; the real name is `users_phone_key`

Rule 8 requires matching `IntegrityError` on the constraint name and names
`uq_users_phone`. The column is declared `unique=True`, so Postgres generated
`users_phone_key` — matching the spec's name would never have fired.
`app/core/integrity.py` maps both, so a future rename does not silently break the
translation.

### "Repositories unchanged" is read as additive-only

Part B rule 5 says every read and write goes through a repository and that a
missing query is *added to the repository, not inlined*; the prerequisite says
repositories are unchanged. Both cannot hold — twelve writes the required business
rules need had no repository method.

Additive only: no existing method's signature or behaviour changed, nothing
removed. The alternative — `session.add(...)` inside services — would have broken
rule 5, which is the one with a grep in the acceptance checklist. Added:
`BookingRepository` (7), `VenueRepository` (5), `UserRepository` (3),
`MenuItemRepository` (5), `MenuCategoryRepository` (1), `VenueZoneRepository` (1),
`VenueServiceRepository` (2), `PaymentCardRepository` (1), `ReviewRepository` (2),
`VenueStaffRepository` (1), `VenueGroupRepository` (2), `OrderRepository` (1).

### Money uses an annotated serializer, not a per-field `field_serializer`

~60 money fields across ~25 schemas. A decorator per field fails open — forget one
and that field ships as a JSON float. `app/core/schemas.py` defines
`Money = Annotated[Decimal, PlainSerializer(...)]` instead: same mechanism,
attached to the type, so a field typed `Money` cannot be serialised any other way.

## Bug found in the repository layer

### `UserRepository.soft_delete` can never commit

It nulls both `phone` and `email`, which violates `ck_users_phone_or_email`
(`phone IS NOT NULL OR email IS NOT NULL`). Any call fails with a
`CheckViolationError`. The Part 1 design decision ("nulls phone/email/avatar") and
the CHECK contradict each other, and the test written for this task is what caught
it.

Worked around, not fixed, since repositories may not be modified: a new
`anonymise_and_soft_delete` releases the **phone to NULL** — so the number can be
registered again, which is the actual goal — and sets the email to
`deleted+{id}@invalid`, a non-identifying tombstone at the reserved `.invalid` TLD
that satisfies the constraint and can never route. `UserService.delete_account`
calls that. The original `soft_delete` is left in place, unused and still broken.

**To fix properly:** either drop `ck_users_phone_or_email`, or change
`soft_delete` to do what the new method does.

## Design notes

### Registration never creates a user before verification

`AuthService.request_code` writes only a hashed code. The `users` row appears on
the first successful `verify_code`. Creating it earlier would let anyone mint rows
for numbers they do not control and collide on `users.phone` when the real owner
signs up. Asserted directly in `test_auth_service.py`.

The failed-attempt path commits before raising — deliberately, in a named helper.
Rolling that back would leave the attempt counter at zero and the five-attempt
lockout would never fire.

### The deposit is subtracted, never added

`_assemble_price_in_transaction` runs base → services → subtotal → promo →
subscription benefit → total → deposit, writing one frozen `booking_price_line`
per component. The deposit line is **negative** and the total is unchanged by it,
because a deposit is a portion of the price paid up front — adding it would charge
the guest twice. Asserted in `test_booking_service.py`.

### Order status is driven by the service, not left at `open`

`add_items` moves an open check to `in_progress`; `add_payment` moves it to
`awaiting_payment` once payments cover the total. Without this the repository's
`close` guard (`served` or `awaiting_payment`) could never be satisfied — found by
the order tests, fixed with the one additive `OrderRepository.set_status`.

### Closing requires payment — Part 2 open question 9, settled

`sum(order_payments.amount) >= total_amount`, else `PaymentIncompleteError`. Cash
is a valid method. A close with no payment row is refused because
`venue_daily_stats.revenue` reads from those rows, and allowing it would make the
dashboard quietly understate the day's takings.

### `business_date` comes from a day-close rule, not `now().date()`

`OrderService.business_date_for` rolls the day at 06:00, so a table opened at 01:30
belongs to the previous business day — which is how the venue counts a night, and
what makes the daily order numbering and the revenue rollup agree.

### Percentage deltas are computed at read and return `None` with no baseline

Growth from zero is undefined, not "+100%". Reporting a number there would invent
a trend from a single data point.

### Push is fire-and-forget, outside the transaction

`NotificationService.notify_in_transaction` writes the row inside the caller's unit
of work — if the booking rolls back, so does the message about it. Delivery happens
after, and its failure is swallowed: a dead push token must never roll back a
booking the database already accepted.

### Secrets

No read schema carries `password_hash`, `code_hash`, `token_hash`,
`temp_password_hash`, `provider_token` or `raw_profile`. `provider_token` appears
only on `PaymentCardCreate`, inbound, because the client must send the token for
the card to be stored at all.

`qr_token` appears on exactly one schema — `BookingOwnerDetail`, the booking
owner's own response. It is a bearer credential for check-in, so it is absent from
every list and every venue-side schema.

The temporary staff password exists in memory only long enough to reach the SMS
transport: never returned, never persisted, never logged. `LoggingSmsSender` logs
the length of a message, not its body.

### `float` in schemas

`distance_m`, `latitude`, `longitude` and `radius_m` are `float`. These are
geographic, not money: PostGIS returns `double precision` from `ST_Distance`, and
the search params feed straight into `ST_GeogFromText`. Every money field is
`Money` (`Decimal`). The checklist scopes the `float` ban to money fields.

## Verification

| Check | Result |
| --- | --- |
| `SCHEMA_PLAN.md` and `SERVICE_PLAN.md` exist | pass |
| `grep -rn "select(\|session.execute\|update(" app/modules/*/services/` | pass — no matches |
| `grep -rn "fastapi\|HTTPException" app/modules/*/services/` | pass — no matches |
| `float` in schemas for money fields | pass — every money field is `Money` |
| No service returns an ORM object | pass — 115 public methods checked at runtime |
| Public writes commit exactly once; no `_in_transaction` commits | pass — AST-verified |
| No enum declared twice | pass — 34 enums, one declaration each, re-exported |
| No read schema exposes a secret | pass |
| `mypy --strict` and `ruff` | pass — 440 files |
| Required tests pass against real Postgres | pass — 36 service tests, 62 total |
| Models and migrations unchanged | pass — 77 models, 19 revisions, autogenerate drift empty |
| Repositories | additive only — see above |

---

# Part 3 — repository layer

45 repositories. No model, migration or constraint was touched; the two problems
found in the models are recorded here and worked around in the repositories.

## Model gaps found (not fixed — this task may not touch models)

### 1. No `relationship()` exists on any model, so `selectinload` has no target

`inspect(Model).relationships` is empty for all 77 models — they declare columns
only. `selectinload` / `joinedload` take a relationship attribute, so the
eager-loading rule cannot be executed literally.

Its *intent* still holds, and more strictly: with no relationships there is
nothing that *can* lazy-load, so async-IO-on-attribute-access is unreachable by
construction. Composite reads return frozen dataclasses assembled from explicit
joins — one round trip rather than `selectinload`'s one-per-collection, and a
typed shape instead of an ORM object whose loaded state depends on how it was
fetched.

Affected: `VenueRepository.get_detail`, `VenueGroupRepository.get_with_branches`,
`StaffRoleRepository.get_with_permissions`, `RegionRepository.get_with_districts`,
`ReviewRepository.list_for_venue`, `BookingRepository.list_for_user`,
`VenueTableQrRepository.get_by_token`, `MenuItemRepository.get_with_variants`,
`VenueServiceRepository.get_with_items`, `ConversationRepository.list_for_user`,
`FavoriteRepository.list_for_user`.

**To fix later:** add `relationship()` declarations to the models. That is an
ORM-level change with no migration, and these methods could then be rewritten to
use `selectinload` without changing their signatures.

### 2. `bookings.checked_in_by_user_id` does not exist

`check_in(booking_id, staff_id, now)` is specified to set it, but neither schema
document defines the column and the models do not have it.

The signature is kept and `staff_id` is written to
`booking_status_history.changed_by_user_id`, which exists for exactly this
purpose and already records the `confirmed → checked_in` transition. Nothing is
lost; the fact lives one join away instead of on the row.

## Changed outside the repositories

### `Page` gained `arbitrary_types_allowed`

`app/core/pagination.py` only. Repositories return `Page[Venue]` and
`Page[VenueSearchRow]`, and pydantic cannot build a core schema for an ORM model
or a plain dataclass without it. API layers returning `Page[SomePydanticSchema]`
validate exactly as before.

A repository has no business converting rows to response schemas, so widening
`Page` was the alternative to inventing a second pagination type.

## Design notes

### Translation fallback is resolved in SQL, once per repository

`DISTINCT ON (parent_id)` ordered by a `CASE` priority of preferred → `uz` → `en`
→ anything. Twelve repositories carry their own copy of this ten-line helper,
which is the intended repetition: each is typed against its own translation table
and can diverge (venues also resolve `tagline`, menu items also `description`)
without a shared abstraction having to grow options.

### `resolve_price` raises rather than falling back

`MenuItemRepository.resolve_price` raises `NotFoundError` when the branch has no
`menu_item_branches` row. Falling back to the catalogue price would be a pricing
bug that only surfaces on a printed receipt: an unticked branch does not sell the
dish at all.

### `next_order_number` locks the venue row

`SELECT venues.id ... FOR UPDATE` before `MAX(order_number) + 1`, which serialises
numbering per branch for the rest of the transaction. The spec allowed either a
lock row or `INSERT ... ON CONFLICT` retry; the venue row already exists and is
the natural lock granularity, so no lock table was invented.

### Group-scoped staff carry permissions at every branch

`VenueStaffRepository.has_permission` treats `venue_staff.venue_id IS NULL` as
group scope — an owner or admin — and matches it at any venue in the chain. That
is why the venue predicate is an `OR` rather than an equality.

### `mark_read` never marks the sender's own messages

`ConversationRepository.mark_read(conversation_id, reader_type, now)` updates only
messages whose `sender_type` differs from the reader's, so opening a thread cannot
mark your own outgoing messages as read.

### `get_by_provider_transaction_id` is scoped by provider

Webhook idempotency keys are only unique within a provider. Two providers can mint
the same reference, and a cross-provider collision would settle the wrong payment.

## Tests

`tests/repositories/`, against a real PostGIS Postgres with the migrations
applied. 19 tests.

Two session fixtures, because they answer different questions:

- `session` — an outer transaction rolled back at teardown. Correct for anything
  single-connection; constraint violations still fire, because Postgres checks
  unique indexes and exclusion constraints at statement time, not at commit.
- `committing_sessions` — two sessions on two real connections that genuinely
  commit, cleaned up by truncating the domain tables. Only these can demonstrate
  one caller winning a race: a savepoint inside one transaction is invisible to a
  second connection, so a single-session "concurrency" test would prove nothing.

The engine is function-scoped because asyncpg connections belong to the event loop
that created them and pytest-asyncio gives each test its own loop. A
session-scoped async engine fails with "another operation is in progress".

The database is `TEST_DATABASE_URL`, else the configured database with `_test`
appended — never the development database, since the suite truncates tables.
`app/alembic/env.py` takes its URL from `settings` by design, so the migration
fixture points `settings.database.url` at the test database rather than trying to
override `alembic.ini`.

## Verification

| Check | Result |
| --- | --- |
| `REPOSITORY_PLAN.md` exists | pass |
| One repository per file | pass — 45 files, AST-verified one `*Repository` class each |
| `grep -r "session.commit" app/modules/*/repositories/` | pass — no matches |
| `grep -rn "except IntegrityError" app/modules/*/repositories/` | pass — no matches (nor `rollback` / `begin`) |
| No `BaseRepository`, no shared CRUD base, no inheritance | pass — every class is standalone |
| `mypy --strict` | pass — 340 files |
| `ruff check` and `ruff format --check` | pass — 367 files |
| Required tests pass against real Postgres | pass — 19 repository tests, 26 total |
| No model, migration or constraint modified | pass — 77 tables, 19 revisions, autogenerate drift empty |

---

# Part 2 — models and migrations

Choices made while generating the 77 models and 19 revisions.

## Things the schema docs left undefined

### `venue_staff` role-scope CHECK needs a denormalized column

The spec requires `CHECK`: role scope `venue` → `venue_id IS NOT NULL`. A Postgres
`CHECK` cannot read another table, and the scope lives on `staff_roles`.

Resolved the standard relational way: `venue_staff.role_scope` is denormalized from
`staff_roles.scope` and held honest by a composite foreign key
`(staff_role_id, role_scope) → staff_roles (id, scope)`, which is why `staff_roles`
carries a `UNIQUE (id, scope)`. The CHECK is then local and real:
`role_scope <> 'venue' OR venue_id IS NOT NULL`.

The alternative was a trigger, which the docs rule out elsewhere ("Denormalized
counters are service-owned. No DB triggers.").

### `refunds.status` values

Part 1 gives `refunds.status` no enum. Used `created, pending, succeeded, failed` —
the payment lifecycle minus `refunded`, which is meaningless on a refund.

### Missing `UNIQUE` on two translation tables

`menu_category_translations` and `menu_item_translations` are the only
`*_translations` tables Part 1 does not give a `UNIQUE (parent_id, language_id)`.
Design decision 10 treats every translation table identically, so this reads as an
omission rather than an intent; the constraint was added to both.

### `amenities.slug` uniqueness

Part 1 marks `venue_types.slug` unique but not `amenities.slug`, though both are
seeded, code-referenced lookup lists. Made unique.

### Column lengths

The docs give lengths only where they matter (`phone` 20, `tagline` 120,
`ticket_code` 16, `qr_token` 32, `last_four` 4, language `code` 5). Everything else
uses conventional sizes: 50 for slugs and codes, 100 for short names, 255 for names
and provider identifiers, `Text` for URLs and free text.

## Deliberate deviations

### `TimestampMixin` applied from the docs' global convention

Both documents state `created_at` / `updated_at` as a stack-wide convention in
their header rather than listing them per table. Applied to all 77 models except
the three pure association tables (`venue_venue_types`, `venue_amenities`,
`staff_role_permissions`), which the docs give no `id` and which therefore take a
composite primary key.

### Postgres image changed to PostGIS

`docker-compose.yml` now uses `postgis/postgis:17-3.5-alpine` instead of
`postgres:17-alpine`. `venues.location` is `geography(Point, 4326)` and the first
revision runs `CREATE EXTENSION postgis`, which plain `postgres:17-alpine` cannot
satisfy.

### `models_registry.py` moved

From `app/core/models_registry.py` to `app/core/database/models_registry.py`, per
this spec. `app/alembic/env.py` updated to match.

### `organization_structure` module removed

A placeholder from the initial scaffold; not one of the 17 Bazmly modules. Removed,
with `app/core/router.py` and `tests/test_health.py` updated.

### `__all__` sorted, imports grouped

The spec asks for "explicit `__all__`, then imports grouped per module". Ruff's
`RUF022` requires `__all__` to be sorted, so `__all__` is alphabetical while the
imports above it stay grouped per module in migration order.

### Seed data is a migration, not `scripts/seed.py`

A data-only revision at the end of the chain. One `alembic upgrade head` then
yields a usable database, and the seed is versioned and reversible alongside the
schema it depends on.

Seeded exactly what the spec lists. `venue_types` and `staff_roles` get their Uzbek
translations as instructed; `service_catalog` also gets Uzbek names, which Part 2
§18 supplies verbatim. `amenities` are seeded as rows only — no document gives
their translated names, so those await content entry.

## How the migrations were produced

### One revision per module, via an autogenerate filter

`app/alembic/env.py` gained an `include_object` hook driven by
`alembic -x only=table_a,table_b revision --autogenerate`. Without the argument
nothing is filtered, so ordinary autogenerate still sees the whole metadata. This is
what let a single `Base.metadata` produce 17 module revisions in dependency order,
each containing only its own tables.

The same hook skips PostGIS's `spatial_ref_sys`, `geography_columns`,
`geometry_columns`, `raster_columns` and `raster_overviews`. They live in `public`
and are owned by the extension, so without this every autogenerate run proposes
dropping them and the no-drift check can never pass.

### Three foreign keys are created late

Listed in [MODEL_PLAN.md](MODEL_PLAN.md). `geo` → `auth` is a genuine cycle
(`user_recent_locations.user_id` → `users`, while `users.district_id` → `districts`),
so that FK is added by the `auth` revision. The two on `promo_code_redemptions`
point forward at `bookings` and `user_subscriptions` and are added by the `bookings`
revision. All three use Postgres's own `<table>_<column>_fkey` naming so
autogenerate recognises them and reports no drift.

### The exclusion constraint and partial indexes did autogenerate

The spec expected all three to need hand-writing. In practice SQLAlchemy 2.0 +
Alembic 1.18 render `postgresql.ExcludeConstraint` inside `create_table`, and
`Index(..., postgresql_where=...)` as a partial index — so all three are declared in
`__table_args__` and generated from there.

That is also what keeps the no-drift check honest: an index created by raw SQL but
absent from the model metadata gets proposed for dropping on the next autogenerate
run. The hand-written SQL was removed once this was confirmed.

### `spatial_index=False` on `venues.location`

GeoAlchemy2 creates a spatial index automatically. The GiST index on `location` is
declared explicitly in `__table_args__` as `ix_venues_location`, so the automatic
one is switched off rather than ending up with two indexes on one column.

### `import geoalchemy2` in the revision template

Autogenerate renders `geoalchemy2.types.Geography(...)` but emits no import for it,
so the generated revision fails at import time. Added to
`app/alembic/script.py.mako`. It is unused in most revisions; `F401` is already
ignored for `app/alembic/versions/*`.

### `ruff check --fix` added as an Alembic post-write hook

`alembic.ini` ran `ruff format` on new revisions but not `ruff check`, so a fresh
revision failed `ruff check` on import sorting. Both hooks now run, lint first.

## Verification

| Check | Result |
| --- | --- |
| `MODEL_PLAN.md` and `DECISIONS.md` exist | pass |
| Every listed file exists, one model per file | pass — 77 files |
| `models_registry.py` imports every model; `len(Base.metadata.tables)` equals model count | pass — 77 / 77 / 77 |
| `alembic upgrade head` on an empty database | pass — 19 revisions |
| `alembic downgrade base` | pass — 19 revisions |
| `alembic revision --autogenerate` after upgrade is empty | pass — `pass` body |
| Exclusion / partial indexes exist in the database | pass — all three verified via `pg_constraint` / `pg_indexes` |
| `ruff check` and `ruff format --check` | pass |
| `mypy` strict | pass — 284 files |
| No model file imports another module's model | pass — asserted in `tests/test_models_registry.py` |

---

# Part 1 — initial scaffold

## Conflicts with the spec

### 1. `/docs` cannot show `/api/v1` and `/api/v2` paths yet

Acceptance check 8 asks that `/docs` show the `/api/v1` and `/api/v2` prefixes.
That is not reachable together with the routing rules, and no code change fixes
it honestly:

- FastAPI's `include_router` **copies routes**; it does not nest router objects.
  A router with zero endpoints contributes zero paths.
- Both `v1` and `v2` module routers are endpoint-free: `v2` because the spec says
  so explicitly ("empty placeholders … Do not duplicate v1 into v2"), `v1`
  because both modules are scaffolded empty.

So OpenAPI currently lists exactly one path, `/api/health`. `/docs` itself
renders (HTTP 200, verified). The prefixes appear the moment the first endpoint
is added to a module router — no wiring change needed.

Rather than inventing placeholder endpoints to make a checklist item go green,
the mounting is asserted directly in
[tests/test_health.py](tests/test_health.py) — `main_router` → `/api`,
`api_v1_router` → `/v1`, `api_v2_router` → `/v2`, and each module router's own
prefix.

### 2. `from typing import AsyncGenerator` in `db_helper.py`

The fixed contents for `db_helper.py` import `AsyncGenerator` from `typing`, but
ruff's `UP` rules (which the spec mandates) reject it as deprecated. Changed to
`from collections.abc import AsyncGenerator`, and the return annotation is
`AsyncGenerator[AsyncSession]` — the trailing `None` argument is flagged by
`UP043` on `target-version = "py314"`. Everything else in that file is verbatim.

## Additions the spec did not mention

### Ports are overridable in `docker-compose.yml`

Published host ports are `${POSTGRES_PORT:-5432}` and `${BACKEND_PORT:-8000}`,
so the spec's defaults hold on a clean machine. Container ports are always 5432
and 8000. This exists because both ports were occupied by unrelated containers
on the verification machine; the stack was verified on `5442`/`8010`.

### Extra exception handler: `StarletteHTTPException`

The spec lists handlers for `AppError`, `RequestValidationError`,
`IntegrityError` and a catch-all `Exception`. Without a `StarletteHTTPException`
handler, 404s and 405s raised by the router itself would bypass the error
envelope and return FastAPI's default `{"detail": ...}` shape. Added one so the
envelope really is universal.

### Validation error details are stripped

`RequestValidationError.errors()` carries `ctx` and `input`, which can hold
non-JSON-serializable objects and echo raw request data back to the client.
`jsonable_errors()` drops both and stringifies `loc`.

### Pydantic settings

- `extra="ignore"` on `Settings.model_config`, so non-`APP_CONFIG__` variables
  in `.env` (`POSTGRES_USER`, `BACKEND_PORT`, …) do not blow up startup.
- Every config section except `database` has a default, so only
  `APP_CONFIG__DATABASE__URL` is strictly required.
- `CorsConfig.origins` defaults to `["*"]` with `allow_credentials=True`. This is
  a scaffold default. **Browsers reject that combination**, and it must be
  narrowed to real origins before this is exposed to one.

### PEP 695 generics

`Page[T]` and `paginate[T: BaseModel]` use Python 3.14's native type-parameter
syntax rather than `Generic[T]` + `TypeVar`. Equivalent, and it is what
`requires-python = ">=3.14"` buys.

### `PaginationParams` is a plain class

Written as a class with an annotated `__init__` rather than a pydantic model or
dataclass — it is the form FastAPI resolves most predictably under
`Annotated[PaginationParams, Depends()]`, and it stays clean under mypy strict.

### `paginate()` counts via a subquery

`select(func.count()).select_from(stmt.order_by(None).subquery())` — wrapping the
caller's statement keeps the count correct through joins, `DISTINCT` and
`GROUP BY`, which a naive `count()` on the root table would get wrong. The
`order_by(None)` strips an ordering Postgres would otherwise reject inside the
subquery.

### `__init__.py` in `app/alembic/` and `app/alembic/versions/`

The target layout does not show them, but hard rule 6 and acceptance check 10
require every directory under `app/` to be a package. Both were added and Alembic
was verified to work with them present — `revision`, `upgrade head`,
`downgrade base` and `current` all behave normally.

### Ruff `per-file-ignores` for migrations

`app/alembic/versions/*` ignores `F401` (generated revisions always import `op`
and `sa`, used or not), `N999` (date-prefixed filenames are not valid module
names) and `E501`.

Mypy excludes the same directory — generated revision bodies are not
strict-clean and are not hand-maintained.

### Ruff as an Alembic post-write hook

`alembic.ini` runs `ruff format` on each newly generated revision, so
`ruff format --check .` keeps passing after `alembic revision`.

### Migration filename template

`%%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s`,
per the spec, plus `truncate_slug_length = 40` to keep filenames sane.

### Docker

- uv is pinned to `ghcr.io/astral-sh/uv:0.10.12` rather than `:latest`, so image
  builds are reproducible.
- Two `uv sync` layers: `--no-install-project --no-dev` before the app code is
  copied (the cached dependency layer), then a full `--locked --no-dev` after.
- Non-root `app` user, uid/gid 1000.
- `.env.template` is deliberately **not** copied into the image. Its localhost
  database URL would otherwise silently mask a missing
  `APP_CONFIG__DATABASE__URL` and produce a confusing connection error instead of
  a clear config error.
- `TZ=UTC` in the image and on both compose services.

### Postgres port is published to the host

`5432` (or `POSTGRES_PORT`) is exposed so `uv run alembic` and psql work from the
host during development. Drop the `ports:` block for anything deployed.

### Tests

`httpx.ASGITransport` drives the app in-process — no network, no database, so
`tests/` stays runnable without a live Postgres. Beyond the required health
check, there are tests for request-id echo, `/docs` rendering, the 404 error
envelope, and the router prefixes.

### Logging

`setup_logging()` clears uvicorn's handlers and sets `propagate = True`, so
uvicorn's output flows through the same formatter and carries the request id.
The format string references `%(request_id)s`, which the `RequestIDFilter`
injects; the filter is attached to the handler, so records from libraries that
never saw the middleware still format cleanly (they log `-`).

## Verification

All twelve acceptance checks were run on this machine. Results, in order:

| # | Check | Result |
| - | ----- | ------ |
| 1 | `uv sync`, `uv.lock` present | pass |
| 2 | `ruff check .`, `ruff format --check .` | pass |
| 3 | `mypy app` strict | pass — 42 files, 0 errors |
| 4 | `pytest` | pass — 5 tests |
| 5 | `docker compose build` | pass |
| 6 | fresh volume → entrypoint migrates → `alembic_version` exists | pass |
| 7 | `curl /api/health` → `{"status": "ok"}` | pass |
| 8 | `/docs` renders; shows `/api/v1` + `/api/v2` prefixes | **partial** — renders (200); prefixes absent, see conflict 1 above |
| 9 | `alembic downgrade base` → `upgrade head` | pass |
| 10 | every directory under `app/` has `__init__.py` | pass — 23/23 |
| 11 | `grep -rn "commit()" app/modules/*/repositories` | pass — no matches |
| 12 | no `BaseRepository` or generic CRUD base | pass — no matches |

Checks 6–9 ran against `POSTGRES_PORT=5442 BACKEND_PORT=8010` because 5432 and
8000 were already bound on this machine.
