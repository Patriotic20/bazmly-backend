from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.core.dependencies import CurrentUser, SessionDep
from app.modules.payments.schemas import (
    PaymentCardCreate,
    PaymentCardRead,
    PaymentCreate,
    PaymentRead,
)
from app.modules.payments.services import PaymentCardService, PaymentService

router = APIRouter(prefix="/v1", tags=["payments"])


@router.get(
    "/payment-cards",
    response_model=list[PaymentCardRead],
    operation_id="payments_list_cards",
    summary="Saqlangan kartalar",
    description="Provayder tokeni hech qachon qaytarilmaydi — u pul yechish kaliti.",
)
async def list_cards(user: CurrentUser, session: SessionDep) -> Sequence[PaymentCardRead]:
    return await PaymentCardService(session).list_for_user(user.id)


@router.post(
    "/payment-cards",
    response_model=PaymentCardRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="payments_add_card",
    summary="Karta saqlash",
    description="Karta raqami bu API ga kelmaydi; mijoz provayder tokenini yuboradi.",
)
async def add_card(
    payload: PaymentCardCreate, user: CurrentUser, session: SessionDep
) -> PaymentCardRead:
    return await PaymentCardService(session).add(user.id, payload)


@router.patch(
    "/payment-cards/{card_id}/default",
    response_model=PaymentCardRead,
    operation_id="payments_set_default_card",
    summary="Asosiy kartani tanlash",
    description="Oldingi asosiy karta shu yozuvda bekor qilinadi.",
)
async def set_default_card(
    user: CurrentUser, session: SessionDep, card_id: Annotated[int, Path(ge=1)]
) -> PaymentCardRead:
    return await PaymentCardService(session).set_default(user.id, card_id)


@router.post(
    "/payments",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="payments_create",
    summary="Bron yoki obunani to'lash",
    description="Faqat bittasi tanlanadi. Oldindan to'lov va qoldiq alohida qatorlar.",
)
async def create_payment(
    payload: PaymentCreate, user: CurrentUser, session: SessionDep
) -> PaymentRead:
    return await PaymentService(session).create_for_booking(user.id, payload)


@router.get(
    "/payments/booking/{booking_id}",
    response_model=list[PaymentRead],
    operation_id="payments_list_for_booking",
    summary="Bron to'lovlari",
    description="Oldindan to'lov va qoldiq bir xil bronga tegishli bo'ladi.",
)
async def list_for_booking(
    user: CurrentUser, session: SessionDep, booking_id: Annotated[int, Path(ge=1)]
) -> Sequence[PaymentRead]:
    return await PaymentService(session).list_for_booking(booking_id)
