from typing import Annotated

from fastapi import APIRouter, Path, status

from app.core.dependencies import CurrentUser, PaginationDep, SessionDep
from app.core.pagination import Page
from app.modules.reviews.schemas import (
    ReviewAggregateRead,
    ReviewCreate,
    ReviewListItem,
    ReviewRead,
)
from app.modules.reviews.services import ReviewService

router = APIRouter(prefix="/v1/reviews", tags=["reviews"])


@router.post(
    "",
    response_model=ReviewRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="reviews_create",
    summary="Sharh qoldirish",
    description="Faqat bron qilgan mijoz va har bron uchun faqat bir marta.",
)
async def create_review(
    payload: ReviewCreate, user: CurrentUser, session: SessionDep
) -> ReviewRead:
    return await ReviewService(session).create(user.id, payload)


@router.get(
    "/venue/{venue_id}",
    response_model=Page[ReviewListItem],
    operation_id="reviews_list_for_venue",
    summary="Muassasa sharhlari",
    description="Chop etilgan sharhlar, muallifi va suratlari bilan.",
)
async def list_for_venue(
    session: SessionDep,
    pagination: PaginationDep,
    venue_id: Annotated[int, Path(ge=1)],
) -> Page[ReviewListItem]:
    return await ReviewService(session).list_for_venue(
        venue_id, pagination.limit, pagination.offset
    )


@router.get(
    "/venue/{venue_id}/aggregate",
    response_model=ReviewAggregateRead,
    operation_id="reviews_aggregate_for_venue",
    summary="Reyting xulosasi",
    description=(
        "O'rtacha baho va sharhlar soni — muassasa kartasidagi reyting shu yerdan hisoblanadi."
    ),
)
async def aggregate_for_venue(
    session: SessionDep, venue_id: Annotated[int, Path(ge=1)]
) -> ReviewAggregateRead:
    return await ReviewService(session).aggregate(venue_id)
