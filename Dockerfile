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

# Dependencies resolve from pyproject.toml + uv.lock before the application is
# copied in, so editing code does not reinstall them: the layer above is reused.
#
# There is deliberately no BuildKit cache mount. Railway's builder demands an
# `id` on one, and then demands that the id carry a prefix naming the service --
# which would tie this file to one service in one account and break the moment
# the service is recreated. A download cache is not worth that.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY alembic.ini ./
COPY docker/ ./docker/
COPY app/ ./app/

RUN uv sync --locked --no-dev

RUN chmod +x /app/docker/entrypoint.sh \
    && groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --no-create-home app \
    && chown -R app:app /app

USER app

EXPOSE 8000

# The entrypoint runs `alembic upgrade head` (on a fresh database that is what
# creates the extensions the schema needs), then hands off to the command.
ENTRYPOINT ["/app/docker/entrypoint.sh"]

# Shell form, because $PORT has to be expanded at run time: Railway assigns the
# port rather than letting the service choose one, and the fallback keeps a
# plain `docker run` working. docker compose overrides this with a fixed port.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
