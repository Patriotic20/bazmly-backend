# bazmly — backend

A FastAPI backend: async SQLAlchemy 2.x, Alembic, PostgreSQL, managed with uv.
The client that consumes it lives in
[bazmly-frontend](https://github.com/Patriotic20/bazmly-frontend); the two share
no code and meet only over HTTP, with the OpenAPI schema at
`/api/openapi.json` as the contract.

Read [CONVENTIONS.md](CONVENTIONS.md) before writing code — the module layout and
the one-model-per-file / no-base-repository rules are not optional.

## Stack

| Concern       | Choice                                        |
| ------------- | --------------------------------------------- |
| Runtime       | Python 3.14                                   |
| Web           | FastAPI + uvicorn                             |
| ORM           | SQLAlchemy 2.x async, `Mapped`/`mapped_column` |
| Migrations    | Alembic (async `env.py`)                      |
| Settings      | Pydantic v2 + pydantic-settings               |
| Database      | PostgreSQL 17 + PostGIS + asyncpg             |
| Cache / locks | Redis                                         |
| Packaging     | uv                                            |
| Lint / format | ruff                                          |
| Types         | mypy `--strict`                               |
| Tests         | pytest + pytest-asyncio                       |

## Quick start

You need a PostgreSQL with **PostGIS** — plain PostgreSQL will not do. The first
migration creates three extensions (`postgis`, `btree_gist`, `pg_trgm`) and the
schema depends on all of them: `venues.location` is a `geography(Point,4326)`,
the no-double-booking rule is a GiST exclusion constraint, and venue search is a
trigram index.

The quickest way to one is a container:

```sh
docker run -d --name bazmly-postgres \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=baz \
  -p 5432:5432 postgis/postgis:17-3.5-alpine
```

Then:

```sh
cp .env.template .env                  # point DATABASE__URL at it
uv sync
uv run alembic upgrade head
uv run python -m scripts.seed_demo     # optional: demo venues, menus, bookings
uv run uvicorn app.main:app --reload
```

**Every command runs from the repository root** — `alembic.ini` resolves
`script_location` against the working directory.

## Deploying to Railway

Built by Nixpacks from [`railway.json`](railway.json); there is no Dockerfile.
The start command runs `alembic upgrade head` before uvicorn, so a fresh
database migrates and seeds its reference data on first boot.

Railway's stock PostgreSQL **does not include PostGIS**. Provision the PostGIS
template instead, or the very first migration fails and the service never
starts.

Variables to set on the service:

| Variable | Value |
| --- | --- |
| `APP_CONFIG__DATABASE__URL` | `${{Postgres.DATABASE_URL}}`, with `postgresql://` rewritten to `postgresql+asyncpg://` |
| `APP_CONFIG__SECURITY__SECRET_KEY` | a real secret — the default is refused outside `local` |
| `APP_CONFIG__ENV` | `production` |
| `APP_CONFIG__CORS__ORIGINS` | `["https://<frontend-domain>"]`, as JSON |
| `APP_CONFIG__TELEGRAM__BOT_TOKEN` | the BotFather token, if Telegram sign-in is wanted |
| `APP_CONFIG__REDIS__URL` | `${{Redis.REDIS_URL}}`, if a Redis service exists |

The asyncpg prefix matters: Railway hands out a `postgresql://` URL and the
driver here is async, so the scheme has to say so.

## Seed data

Two layers, and they are not interchangeable.

**Reference data ships in migrations**, so `alembic upgrade head` alone yields a
database the app can run on: the three interface languages (`uz`, `en`, `ru`),
staff roles, permissions, the service catalogue, amenities, and the whole
geography — 14 regions and 209 districts of Uzbekistan, keyed by ISO 3166-2:UZ
codes, with a centre coordinate per district. `venues.district_id` is NOT NULL,
so onboarding is impossible without the last of those.

**Demo data is a script**, because none of it belongs in staging or production:

```sh
uv run python -m scripts.seed_demo
```

It writes three chains, six branches (four restaurants and two to'yxona), their
zones, tables, working hours, photos, amenities, guest tiers, menus, services,
staff, bookings, open checks, reviews and favourites, plus 29 accounts — one
admin, one moderator, three owners, six customers and eighteen employees. Every
account signs in with the phone number printed at the end and the password
`demo1234`.

Each run truncates the demo-owned tables first, so it is idempotent. It never
touches `regions` or `districts`, and it refuses to run unless
`APP_CONFIG__ENV=local`.

## Checks

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
```

## Configuration

Settings are nested and namespaced. Every variable is `APP_CONFIG__` prefixed and
nested with a double underscore:

```
APP_CONFIG__DATABASE__URL=postgresql+asyncpg://postgres:postgres@localhost:5432/baz
APP_CONFIG__RUN__PORT=8000
APP_CONFIG__LOGGING__LEVEL=INFO
APP_CONFIG__ENV=local
```

Signing in needs no third party. A customer sends a phone number, then a name and
an optional password, and the account exists — there is no verification code, no
SMS gateway, no email and no external dependency.

`APP_CONFIG__SECURITY__AUTH_MODE` is coupled to `ENV`. Setting it to
`disabled` — together with `APP_CONFIG__SECURITY__DEV_USER_ID`, a real `users.id`
— turns off authentication *and* authorization at every layer, so the API can be
driven from a browser before a login flow exists. It is refused outside
`ENV=local`: the process will not start. The default is `enforced`.

[`.env.template`](.env.template) is committed and holds safe defaults; `.env` is
git-ignored and overrides it. Both are loaded, in that order, and both are
addressed by absolute path — the settings a process gets do not depend on the
directory it was launched from.

In a deployment there is no `.env` at all: the same names are set as environment
variables, which take precedence over both files.

## Layout

```
app/
├── main.py                 # app wiring, middleware, lifespan
├── core/                   # config, routing, errors, pagination, logging, db
│   ├── database/           # Base, mixins, DatabaseHelper
│   └── middleware/         # request id, access logging
├── modules/                # feature modules — auth, organization_structure
└── alembic/                # migration environment
```

`course`, `quiz` and `psychology` come later and must use the identical module
skeleton — see [CONVENTIONS.md](CONVENTIONS.md).

## Migrations

```sh
uv run alembic revision --autogenerate -m "add users"
uv run alembic upgrade head
uv run alembic downgrade -1
```

New models must be imported in [`app/core/models_registry.py`](app/core/models_registry.py)
or autogenerate will not see them.

The database URL comes from `settings.database.url`, never from `alembic.ini`.

## API

| Route                  | Purpose                                |
| ---------------------- | -------------------------------------- |
| `GET /api/health`      | Liveness. Does not touch the database. |
| `/api/v1/<module>/...` | Versioned module endpoints.            |
| `/api/v2/<module>/...` | Reserved; no endpoints yet.            |
| `/api/docs`            | Swagger UI.                            |
| `/api/openapi.json`    | OpenAPI schema.                        |

The docs and schema sit under the API prefix so a reverse proxy can route one path
to this service.

Errors always come back in one envelope:

```json
{"code": "not_found", "message": "...", "details": {}, "request_id": "..."}
```

`message` is Uzbek and is for display only. Branch on `code` — it is English and
stable.

Every response carries an `X-Request-ID` header, echoed from the request when
supplied and generated otherwise.
