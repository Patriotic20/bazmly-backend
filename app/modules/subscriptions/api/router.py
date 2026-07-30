from fastapi import APIRouter

from app.modules.subscriptions.api.v1.router import router as v1_router
from app.modules.subscriptions.api.v2.router import router as v2_router

router = APIRouter()
router.include_router(v1_router)
router.include_router(v2_router)
