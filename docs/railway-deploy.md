# Deploying to Railway

Two services: a Postgres built from the PostGIS template, and this backend built
from the repository `Dockerfile`. Redis is deliberately not deployed — the
availability cache falls back to `InMemoryAvailabilityCache`, which is correct
but per-worker (see `app/core/cache.py`). Add Redis when a shared cache is worth
paying for.

`railway.toml` at the repository root configures the backend service: Dockerfile
builder, `/api/health` healthcheck, restart-on-failure. Everything below is the
part Railway cannot read from the repository.

## 1. Create the Postgres service

In the Railway project: **New → Database → Add PostgreSQL**, then swap it for the
PostGIS variant, or deploy the **PostGIS** template directly from the template
marketplace.

The plain PostgreSQL template will not work. The first migration
(`app/alembic/versions/2026_07_30_0957-229d06409d72_extensions.py`) runs

```sql
CREATE EXTENSION IF NOT EXISTS postgis
CREATE EXTENSION IF NOT EXISTS btree_gist
CREATE EXTENSION IF NOT EXISTS pg_trgm
```

and `venues.location` is `geography(Point, 4326)`. Without PostGIS the deploy
fails during `alembic upgrade head`, before uvicorn ever binds a port.

Note the service name Railway gives it. The variable references in the next step
assume it is `Postgres`; rename them to match if it is not.

## 2. Create the backend service

**New → GitHub Repo**, point it at this repository. Railway finds `railway.toml`
and builds from the `Dockerfile`. No start command needs to be set — the image's
`ENTRYPOINT` runs `alembic upgrade head` and its `CMD` binds `$PORT`, which
Railway injects.

## 3. Set the backend's variables

`.env.template` is not copied into the image, so nothing is inherited from it —
every value below has to exist in Railway. Settings are namespaced
`APP_CONFIG__` and nested with `__` (see `app/core/config.py`).

| Variable | Value |
| --- | --- |
| `APP_CONFIG__DATABASE__URL` | `postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}` |
| `APP_CONFIG__ENV` | `production` |
| `APP_CONFIG__SECURITY__SECRET_KEY` | 32+ random bytes — generate, do not invent |
| `APP_CONFIG__SECURITY__AUTH_MODE` | `enforced` |
| `APP_CONFIG__CORS__ORIGINS` | JSON array of the front-end origins, e.g. `["https://app.example.com"]` |
| `APP_CONFIG__LOGGING__LEVEL` | `INFO` |

`${{Postgres.*}}` is Railway's variable-reference syntax; it resolves at deploy
time against the Postgres service. Writing the URL this way is why no code
translates schemes: Railway's own `DATABASE_URL` is `postgresql://`, and the
engine needs `postgresql+asyncpg://`. Building the URL from the parts avoids a
string rewrite in the application.

`RAILWAY_PRIVATE_DOMAIN` keeps database traffic on the private network, so the
Postgres service never needs a public TCP proxy.

Generate the secret with:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

One of these is enforced, one is not. With `APP_CONFIG__ENV=production`,
`validate_auth_settings` in `app/core/auth_mode.py` refuses to start the process
if `AUTH_MODE` is `disabled` — that misconfiguration crashes rather than quietly
serving unauthenticated traffic.

`SECRET_KEY` has no such guard. Nothing checks it at startup, so a deploy that
omits it runs happily on the placeholder in `app/core/config.py` — a signing key
published in this repository, which means anyone can mint an access token for
any user. Setting it is not optional.

`APP_CONFIG__RUN__PORT` is not in the table on purpose. It only affects
`python -m app.main`, which the container does not use; the container's port
comes from `$PORT` via the Dockerfile `CMD`.

## 4. Expose the backend

**Settings → Networking → Generate Domain** on the backend service. Railway
detects the port from `$PORT`. Swagger is then at `<domain>/api/docs`.

## Migrations

`docker/entrypoint.sh` runs `alembic upgrade head` on every container start, so
each deploy migrates before serving. Two consequences worth knowing:

- A failing migration fails the deploy. Railway keeps the previous deployment
  serving, which is the behaviour you want.
- Scaling to multiple replicas means concurrent `alembic upgrade head` runs
  racing each other. Each runs its DDL in a transaction and updates the same
  `alembic_version` row, so Postgres serialises them, but concurrent DDL on the
  same tables can still deadlock and fail a deploy. Keep replicas at 1 until
  migrations move to a release step of their own.

## Troubleshooting

**Deploy fails with `permission denied to create extension "postgis"`** — the
database role is not a superuser and the template did not pre-install the
extension. Open the Postgres service's shell and run the three `CREATE EXTENSION`
statements above as the superuser, then redeploy: the migration's
`IF NOT EXISTS` makes it a no-op the second time.

**Healthcheck times out on the first deploy** — the initial `alembic upgrade
head` applies every migration before uvicorn binds. `healthcheckTimeout` in
`railway.toml` is 300s for this reason; raise it if the baseline grows.

**Healthcheck passes but the API returns database errors** — `/api/health`
answers `200` with `{"status": "degraded", "database": "down"}` when it cannot
reach Postgres. It reports the failure but does not fail the check, so Railway
will happily route to a backend that has lost its database.
