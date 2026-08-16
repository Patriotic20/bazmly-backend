# uv is copied in from the official distroless image rather than pip-installed,
# and the base image already carries Python 3.14 — which is what makes this
# reliable where the platform's own builder is not. Nixpacks has no 3.14 and
# pins uv 0.4.30, too old to read this project's `revision = 3` lockfile.
FROM ghcr.io/astral-sh/uv:0.10.12 AS uv

FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies resolve from pyproject.toml + uv.lock in their own cached layer,
# so editing application code does not invalidate the install.
#
# The cache mounts carry an explicit `id`. BuildKit treats it as optional and
# derives one from the target path, but Railway's builder rejects a mount
# without it -- so omitting it builds locally and fails there.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY alembic.ini ./
COPY app/ ./app/

RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --no-create-home app \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Shell form, because $PORT has to be expanded at run time: Railway assigns the
# port rather than letting the service choose one, and the fallback keeps a
# plain `docker run` working.
#
# Migrations run here rather than in an entrypoint script so that the whole
# start sequence is visible in one place — and on a fresh database this is what
# creates the postgis, btree_gist and pg_trgm extensions the schema needs.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
