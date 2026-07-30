from fastapi import APIRouter

# Placeholder. v2 exists so the shape is uniform across modules; it is never a
# mirror of v1 and gains endpoints only when a breaking change needs one.
router = APIRouter(prefix="/v2/orders", tags=["orders:v2"])
