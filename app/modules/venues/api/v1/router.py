from fastapi import APIRouter

from app.modules.venues.api.v1.customer import router as customer_router
from app.modules.venues.api.v1.venue import router as venue_router

router = APIRouter()
router.include_router(customer_router)
router.include_router(venue_router)
