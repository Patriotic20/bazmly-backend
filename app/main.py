from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database.db_helper import db_helper
from app.core.handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware.logging import LoggingMiddleware
from app.core.middleware.request_id import RequestIDMiddleware
from app.core.router import main_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    setup_logging()
    yield
    await db_helper.dispose()


app = FastAPI(
    lifespan=lifespan,
    title="Bazmly API",
    version="1.0.0",
    summary="Booking and venue management for restaurants and to'yxona.",
    description=(
        "Two audiences share this API. Customer routes live under `/api/v1/<module>`; "
        "staff routes live under `/api/v1/venue/...` and are guarded by a permission "
        "check against `venue_staff`, never by a claim in the token — so a role change "
        "takes effect immediately rather than at the next token expiry.\n\n"
        "Every error returns the same flat body: `code`, `message`, `details`, "
        "`request_id`."
    ),
    # Under the API prefix so a reverse proxy can route one path to this service.
    docs_url=f"{settings.api.prefix}/docs",
    redoc_url=f"{settings.api.prefix}/redoc",
    openapi_url=f"{settings.api.prefix}/openapi.json",
    openapi_tags=[
        {"name": "auth", "description": "Registration, sign-in and token rotation."},
        {"name": "users", "description": "Profile, devices and friends."},
        {"name": "venues", "description": "Customer-facing venue search and detail."},
        {"name": "venue:venues", "description": "Filiallar — branch management."},
        {"name": "venue:staff", "description": "Hodimlar — employment and invitations."},
        {"name": "venue:menu", "description": "Menyu builder."},
        {"name": "bookings", "description": "Customer bookings — the Joylar tab."},
        {"name": "venue:bookings", "description": "Kutilayotgan mijozlar — the day queue."},
        {"name": "venue:orders", "description": "Buyurtmalar — open checks on tables."},
        {"name": "venue:analytics", "description": "Dashboard and reports."},
        {"name": "webhooks", "description": "Payment provider callbacks. No JWT."},
    ],
)

# Middleware order as executed per request: CORS -> request id -> logging.
# Starlette runs middleware outermost-last-added, so they are added in reverse.
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors.origins,
    allow_credentials=settings.cors.allow_credentials,
    allow_methods=settings.cors.allow_methods,
    allow_headers=settings.cors.allow_headers,
)

register_exception_handlers(app)
app.include_router(main_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.run.host,
        port=settings.run.port,
        reload=settings.run.reload,
    )
