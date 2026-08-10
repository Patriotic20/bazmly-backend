from collections.abc import Sequence

from fastapi import APIRouter

from app.core.dependencies import SessionDep
from app.modules.catalog.schemas import AmenityRead
from app.modules.catalog.services import CatalogService

router = APIRouter(prefix="/v1", tags=["catalog"])


@router.get(
    "/amenities",
    response_model=list[AmenityRead],
    operation_id="catalog_list_amenities",
    summary="Qulayliklar ro'yxati",
    description="Parkovka, ovoz tizimi, sahna, konditsioner, professional oshxona, Wi-Fi.",
)
async def list_amenities(session: SessionDep) -> Sequence[AmenityRead]:
    return await CatalogService(session).list_amenities()
