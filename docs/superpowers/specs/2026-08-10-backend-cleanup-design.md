# Backend cleanup: auth surface, venue types, geo reference data, docs

**Date:** 2026-08-10
**Status:** approved, pending implementation plan

Five independent changes, sequenced into phases that can be stopped between. Three
of them carry an Alembic migration; those three run one at a time so each migration
has a single clear parent.

## Scope

| Phase | Change | Migration |
|---|---|---|
| 1 | Swagger renders auth as a Bearer security scheme | no |
| 2 | Remove Google authentication | yes |
| 3 | Venue types become a two-value enum | yes |
| 4 | Geo: admin CRUD for regions/districts + full Uzbek seed | yes |
| 5 | Root `.md` files reorganized into `docs/` | no |

**Out of scope.** Localization was investigated and dropped: `languages` is already
seeded with exactly `uz`, `en`, `ru` in
`app/alembic/versions/2026_07_30_1007-b7834c92fef5_seed_reference_data.py`, which is
what was asked for. Translation *content* remains Uzbek-only by a prior deliberate
migration (`collapse_translations_to_uzbek_only`) and stays that way.

Map-based coordinate capture also needs no work. `Venue`, `UserRecentLocation`, and
`UserAddressCreate` already take `district_id` plus required
`latitude`/`longitude`, and `venue_repository` already runs PostGIS distance
queries against them. The gap was never the coordinate plumbing — it was that the
region and district tables are empty and have no write endpoints.

---

## Phase 1 — Bearer security scheme

### Problem

`app/core/dependencies.py` declares auth as an ordinary nullable header —
`authorization: Annotated[str | None, Header()] = None` at three call sites
(`get_current_user`, `get_current_user_pending_ok`, `get_current_user_optional`) —
and strips the `bearer ` prefix by hand in `_bearer_token`.

FastAPI has no way to know that header is a credential, so Swagger draws every
protected endpoint with an optional `authorization` text box typed
`string | (string | null)`. A protected route reads as public. This was reported
against `GET /api/v1/venue/groups`, which does enforce `CurrentUser` and is
owner-only.

### Change

One module-level `HTTPBearer(auto_error=False)` instance replaces all three header
params. `BEARER_PREFIX` and `_bearer_token` are deleted — `HTTPBearer` yields
parsed `scheme` and `credentials`.

`auto_error=False` matters: it makes the scheme return `None` rather than raising,
which preserves `get_current_user_optional`'s contract and keeps every failure a
`DomainError` decided by `app/core/handlers.py`. Nothing in `dependencies.py` may
start raising `HTTPException`.

The dev-mode bypass (`auth_disabled` / `dev_user_id` from `app.core.auth_mode`)
must keep working with no credential present.

### Verification

Behavior is unchanged, so the existing auth tests are the regression net. Add a
check that `/openapi.json` carries an `HTTPBearer` entry under
`components.securitySchemes` and that a protected operation references it, so this
cannot silently regress. Confirm by eye that `/docs` shows one Authorize button.

---

## Phase 2 — Remove Google authentication

### What Google touches

- `app/core/integrations/google/` (`verifier.py`, `__init__.py`) — delete
- `POST /v1/auth/social/google` in `app/modules/auth/api/v1/auth.py` — delete
- `google_login`, `_verify_google`, `_create_google_user_in_transaction` in
  `app/modules/auth/services/auth_service.py` — delete
- `GoogleLogin` schema and its `__init__` export — delete
- Google client settings in `app/core/config.py` and `.env.template` — delete
- the Google-specific `DomainError` subclass in `app/core/exceptions.py` and its
  branch in `app/core/handlers.py` — delete
- any Google wiring in `app/main.py` — delete

### The table goes too

`AuthProvider` has exactly one member, `GOOGLE`. With Google gone the enum has no
values and `AuthIdentity` has nothing to hold, so the model, the enum, the
`auth_identities` table, and the `AuthProvider` re-export from
`app/modules/auth/enums.py` are all removed.

The model's own docstring argues for keeping a table so a second provider is just a
row. That argument dies with the last provider; if a provider is ever added it comes
back as a new table in a new migration.

Auth still functions afterward: `/v1/auth/register`, `/v1/auth/login`, and
`/v1/auth/staff-login` are phone + password and do not involve Google.

### Blocking pre-flight

Before writing the drop migration, run:

```sql
SELECT count(*) FROM users u
JOIN auth_identities ai ON ai.user_id = u.id
WHERE u.password_hash IS NULL;
```

A non-zero result means those users signed in with Google only and dropping the
table locks them out permanently. Report the count and stop for a decision — do not
choose a remediation unilaterally. Zero means proceed.

### Verification

Auth tests pass. `grep -ri google app/ .env.template` returns only historical
Alembic migration files, which are immutable and must not be edited.

---

## Phase 3 — Venue types as a two-value enum

### Change

A `VenueTypeSlug(StrEnum)` with `RESTORAN = "restoran"` and `TOYXONA = "toyxona"`,
declared in the venues module's enums and re-exported the way the codebase already
re-exports enums from models.

- `Venue` gains a `venue_type` enum column.
- `venue_groups.primary_venue_type_id` (FK) becomes a `primary_venue_type` enum
  column.
- Dropped: the `venue_venue_types` and `venue_types` tables, the `VenueType` model,
  `VenueTypeRepository`, and the venue-type translation rows.
- `GET /v1/venue-types` (`list_venue_types` in
  `app/modules/catalog/api/v1/router.py`) is deleted.
- Venue search changes from `venue_type_ids: list[int]` and the
  `VenueVenueType` subquery in `venue_repository.py` to a single `venue_type`
  equality filter. `venue_service.py` and `venue_onboarding_service.py` drop their
  `get_by_id` existence checks — an invalid value now fails at schema validation.

### Two judgment calls, decided

**`icon_url` and `sort_order` disappear.** The endpoint that served them is being
deleted, so the client owns presentation. A small label map beside the enum —
`{RESTORAN: ("Restoran", 1), TOYXONA: ("To'yxona", 2)}` — supplies the Uzbek display
name and ordering wherever an API response still needs one. Icons move to the
client.

**`kafe` maps to `restoran`.** It is still in the seed migration even though the
running database returns only two types. The migration counts `kafe`-typed venues
first and logs the number, then folds them into `restoran`. If the count is large
enough to be surprising, surface it rather than silently rewriting rows.

### Migration order

Add both columns, then backfill, then drop. Backfill before dropping, never after.

- `venues.venue_type` comes from `venue_venue_types`. A venue with more than one type
  takes its lowest `sort_order` type, so `restoran` wins over `toyxona` and both win
  over `kafe`.
- `venue_groups.primary_venue_type` is a direct slug lookup through the existing
  `primary_venue_type_id` FK.
- Any row still resolving to `kafe` after that becomes `restoran`.

### Verification

Venue search and onboarding tests pass. A venue created through onboarding round-trips
its type. No table in the schema references `venue_types`.

---

## Phase 4 — Geo: admin CRUD and full Uzbek reference data

### Platform-admin dependency

None exists. `UserRole.ADMIN` is on the user model but nothing guards on it —
`require_permission` and `require_group_permission` are *staff* roles scoped to a
venue group, which is a different axis entirely and must not be reused here.

Add `require_platform_role(UserRole.ADMIN)` to `app/core/dependencies.py`, exposed
as an `AdminUser` annotation, following the shape of the existing guard classes and
raising `PermissionDeniedError` — not `HTTPException`.

### Endpoints

Reads stay public; customers need the dropdowns before they authenticate. The v1 geo
router currently carries `prefix="/v1/regions"`, so districts get their own router
and both are included from `app/modules/geo/api/router.py`.

```
GET    /v1/regions                  public   (exists)
GET    /v1/regions/{id}/districts   public   (exists)
POST   /v1/regions                  admin
PATCH  /v1/regions/{id}             admin
DELETE /v1/regions/{id}             admin
POST   /v1/districts                admin
PATCH  /v1/districts/{id}           admin
DELETE /v1/districts/{id}           admin
```

New `RegionCreate`/`RegionUpdate` and `DistrictCreate`/`DistrictUpdate` schemas.
`DistrictCreate` requires `latitude` and `longitude` because the column is already
`nullable=False`; both are bounded to Uzbekistan's envelope so a transposed
lat/lng is rejected at the edge.

Only `location_service.py` exists today, and it is read-only. Writes go in
`region_service.py` and `district_service.py` so no single file owns both the
customer read path and the admin write path.

Delete refuses while anything still references the row — a region with districts, or
a district with a venue or a `user_recent_location` — raising `ValidationFailedError`
with an Uzbek message rather than surfacing a raw FK violation.

`Region.code` uses ISO 3166-2:UZ (`UZ-TK`, `UZ-AN`, …) and is unique — it is
currently `nullable=False` but not constrained, so the migration adds the
constraint.

**Region gets no coordinates.** It stays `name` + `code`. Nothing in the app needs a
viloyat centre point, and one can be derived from its districts if that ever changes.

### Seed data

14 regions — 12 viloyats, Qoraqalpogʻiston Republic, and Toshkent city — plus every
district and city under them, roughly 200 rows, each with the required
`latitude`/`longitude`.

The rows are embedded in the migration file rather than read from an external data
file, so the migration stays self-contained and cannot change meaning when a data
file is edited later.

**Data-integrity constraint on the implementer:** these are real coordinates. Build
the dataset from a public source (OpenStreetMap or GeoNames administrative
boundaries), not from recall. Any district whose coordinates cannot be sourced
confidently is listed explicitly for the user to fill in — do not emit a
plausible-looking number to close a gap. The user will spot-check their own region.

### Verification

Admin endpoints reject a `customer`-role token with 403 and accept an `admin` token.
Reads stay reachable unauthenticated. Delete of a referenced district returns a
validation error, not a 500. Post-seed row counts are asserted: 14 regions, and every
district resolves to a real region.

---

## Phase 5 — Docs reorganization

Deliberately last. Phases 2–4 each record a decision in `DECISIONS.md`; letting them
write to it in place and then moving the settled file avoids editing the same
document in five places across five phases.

```
README.md                     stays in root, trimmed to an index that links into docs/
docs/conventions.md           ← CONVENTIONS.md
docs/decisions.md             ← DECISIONS.md, trimmed of resolved and superseded entries
docs/architecture/api.md          ← API_PLAN.md
docs/architecture/model.md        ← MODEL_PLAN.md
docs/architecture/repository.md   ← REPOSITORY_PLAN.md
docs/architecture/schema.md       ← SCHEMA_PLAN.md
docs/architecture/service.md      ← SERVICE_PLAN.md
```

`docs/` already exists and holds `bazmly-db-schema.md` and
`db-schema-part2-venue-app.md`; those stay where they are.

README stays in the root because GitHub renders it as the repository landing page.

`make_plan.md` reads as a scratch prompt rather than project documentation. Read it
and propose keep-or-delete; do not move it blindly.

"Optimize" means removing content that the code now states more accurately and
merging passages that repeat each other — the five `*_PLAN.md` files total 784 lines
and overlap. It does not mean rewriting decisions or dropping rationale. `DECISIONS.md`
is 1,161 lines and is where the trimming pays off most.

Use `git mv` so history follows each file.

**Cross-references must be updated.** Code docstrings cite these files by name —
`app/modules/auth/enums.py` says "See DECISIONS.md for why the declarations still sit
in the models", and there are others. Grep for every `*.md` filename across `app/`
and the remaining docs, and fix each reference in the same commit as the move so the
tree is never left pointing at a path that does not exist.

---

## Risks

- **Phase 2 can strand users.** Mitigated by the blocking pre-flight query. This is
  the only phase that can destroy access, and it stops for a human decision.
- **Phase 3 rewrites venue rows.** The backfill runs before any drop, and `kafe`
  counts are reported rather than silently folded.
- **Phase 4's dataset is large and externally sourced.** Gaps are surfaced, never
  filled with invented coordinates.
- **Phase 5 touches a file every other phase writes to.** Resolved by ordering it
  last.

Each phase is independently shippable and independently revertible. Stopping after
any phase leaves a working API.
