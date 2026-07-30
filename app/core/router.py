"""The single mount point for every module router.

Each module owns its own `/v1/<module>` prefix, so this file only says *which*
modules exist — adding a route never touches it, and the version lives next to the
endpoints it versions rather than in one central place that drifts.
"""

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.database.db_helper import db_helper
from app.core.webhooks import router as webhooks_router
from app.modules.analytics.api import router as analytics_router
from app.modules.auth.api import router as auth_router
from app.modules.bookings.api import router as bookings_router
from app.modules.catalog.api import router as catalog_router
from app.modules.engagement.api import router as engagement_router
from app.modules.geo.api import router as geo_router
from app.modules.localization.api import router as localization_router
from app.modules.menu.api import router as menu_router
from app.modules.orders.api import router as orders_router
from app.modules.payments.api import router as payments_router
from app.modules.promotions.api import router as promotions_router
from app.modules.reviews.api import router as reviews_router
from app.modules.services.api import router as services_router
from app.modules.staff.api import router as staff_router
from app.modules.subscriptions.api import router as subscriptions_router
from app.modules.venue_groups.api import router as venue_groups_router
from app.modules.venues.api import router as venues_router

API_VERSION = "1.0.0"

main_router = APIRouter(prefix=settings.api.prefix)


@main_router.get(
    "/health",
    response_model=dict[str, Any],
    operation_id="health_check",
    summary="Health check",
    description="Build info plus a database ping. Outside versioning by design.",
)
async def health() -> dict[str, Any]:
    """Pings the database rather than only reporting that the process is up.

    A process that cannot reach Postgres is not healthy, and a load balancer that
    keeps routing to it turns one broken pod into a broken deployment.
    """
    database_ok = True
    try:
        async for session in db_helper.session_getter():
            await session.execute(text("SELECT 1"))
            break
    except Exception:
        database_ok = False

    return {
        "status": "ok" if database_ok else "degraded",
        "version": API_VERSION,
        "database": "up" if database_ok else "down",
    }


for module_router in (
    localization_router,
    geo_router,
    catalog_router,
    auth_router,
    venue_groups_router,
    venues_router,
    staff_router,
    menu_router,
    services_router,
    bookings_router,
    orders_router,
    payments_router,
    subscriptions_router,
    promotions_router,
    reviews_router,
    engagement_router,
    analytics_router,
    webhooks_router,
):
    main_router.include_router(module_router)
