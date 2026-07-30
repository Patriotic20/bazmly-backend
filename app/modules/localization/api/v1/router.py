from collections.abc import Sequence

from fastapi import APIRouter

from app.core.dependencies import SessionDep
from app.modules.localization.schemas import LanguageRead
from app.modules.localization.services import LanguageService

router = APIRouter(prefix="/v1/languages", tags=["localization"])


@router.get(
    "",
    response_model=list[LanguageRead],
    operation_id="localization_list_languages",
    summary="Tillar ro'yxati",
    description="Til sozlamalari ekranida aynan shu tillar taklif qilinadi.",
)
async def list_languages(session: SessionDep) -> Sequence[LanguageRead]:
    return await LanguageService(session).list_active()
