# uv is copied in from the official distroless image rather than pip-installed.
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
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY alembic.ini ./
COPY docker/ ./docker/
COPY app/ ./app/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

RUN chmod +x /app/docker/entrypoint.sh \
    && groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --no-create-home app \
    && chown -R app:app /app

USER app

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
