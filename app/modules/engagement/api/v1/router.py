from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.core.dependencies import CurrentUser, LanguageId, PaginationDep, SessionDep
from app.core.pagination import Page
from app.modules.engagement.enums import MessageSenderType
from app.modules.engagement.schemas import (
    ConversationCreate,
    ConversationListItem,
    ConversationRead,
    FavoriteCreate,
    FavoriteRead,
    FavoriteToggled,
    MessageCreate,
    MessageRead,
    NotificationRead,
    UnreadCountRead,
)
from app.modules.engagement.services import (
    ConversationService,
    FavoriteService,
    NotificationService,
)

router = APIRouter(prefix="/v1", tags=["engagement"])


@router.get(
    "/favorites",
    response_model=list[FavoriteRead],
    operation_id="engagement_list_favorites",
    summary="Sevimli muassasalar",
    description="Xatcho'p belgisi orqali saqlangan muassasalar.",
)
async def list_favorites(
    user: CurrentUser, language_id: LanguageId, session: SessionDep
) -> Sequence[FavoriteRead]:
    return await FavoriteService(session).list_for_user(user.id, language_id)


@router.post(
    "/favorites",
    response_model=FavoriteToggled,
    operation_id="engagement_toggle_favorite",
    summary="Sevimlini almashtirish",
    description=(
        "Idempotent: bitta yo'l, shuning uchun qo'shish va olib tashlash ziddiyatga tushmaydi."
    ),
)
async def toggle_favorite(
    payload: FavoriteCreate, user: CurrentUser, session: SessionDep
) -> FavoriteToggled:
    return await FavoriteService(session).toggle(user.id, payload.venue_id)


@router.delete(
    "/favorites/{venue_id}",
    response_model=FavoriteToggled,
    operation_id="engagement_remove_favorite",
    summary="Sevimlidan olib tashlash",
    description="Natijaviy holatni qaytaradi, shunda mijoz ilovasi taxmin qilmaydi.",
)
async def remove_favorite(
    user: CurrentUser, session: SessionDep, venue_id: Annotated[int, Path(ge=1)]
) -> FavoriteToggled:
    return await FavoriteService(session).toggle(user.id, venue_id)


@router.get(
    "/conversations",
    response_model=list[ConversationListItem],
    operation_id="engagement_list_conversations",
    summary="Suhbatlar",
    description="Oxirgi xabar va o'qilmaganlar soni bilan birga.",
)
async def list_conversations(
    user: CurrentUser, session: SessionDep
) -> Sequence[ConversationListItem]:
    return await ConversationService(session).list_for_user(user.id)


@router.post(
    "/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="engagement_open_conversation",
    summary="Suhbat ochish",
    description=(
        "Xabar yuborish. Har bir mijoz va muassasa uchun bitta suhbat, har bron uchun emas."
    ),
)
async def open_conversation(
    payload: ConversationCreate, user: CurrentUser, session: SessionDep
) -> ConversationRead:
    return await ConversationService(session).open(user.id, payload.venue_id, payload.booking_id)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageRead],
    operation_id="engagement_list_messages",
    summary="Xabarlar tarixi",
    description="Eng yangisidan boshlab, sahifalab.",
)
async def list_messages(
    user: CurrentUser,
    session: SessionDep,
    pagination: PaginationDep,
    conversation_id: Annotated[int, Path(ge=1)],
) -> Sequence[MessageRead]:
    return await ConversationService(session).history(
        conversation_id, pagination.limit, pagination.offset
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="engagement_send_message",
    summary="Xabar yuborish",
    description="Suhbatning `last_message_at` maydoni ham shu yozuvda yangilanadi.",
)
async def send_message(
    payload: MessageCreate,
    user: CurrentUser,
    session: SessionDep,
    conversation_id: Annotated[int, Path(ge=1)],
) -> MessageRead:
    return await ConversationService(session).send(
        conversation_id, user.id, MessageSenderType.USER, payload
    )


@router.post(
    "/conversations/{conversation_id}/read",
    response_model=list[int],
    operation_id="engagement_mark_conversation_read",
    summary="Suhbatni o'qilgan deb belgilash",
    description=(
        "Faqat qarshi tomon xabarlari belgilanadi — yuboruvchi o'z xabarini belgilamaydi."
    ),
)
async def mark_conversation_read(
    user: CurrentUser, session: SessionDep, conversation_id: Annotated[int, Path(ge=1)]
) -> Sequence[int]:
    return await ConversationService(session).mark_read(conversation_id, MessageSenderType.USER)


@router.get(
    "/notifications",
    response_model=Page[NotificationRead],
    operation_id="engagement_list_notifications",
    summary="Xabarlar",
    description="Mijoz ilovasi `sent_at` bo'yicha Bugun / Shu hafta / Shu oy ga ajratadi.",
)
async def list_notifications(
    user: CurrentUser, session: SessionDep, pagination: PaginationDep
) -> Page[NotificationRead]:
    return await NotificationService(session).list_for_user(
        user.id, pagination.limit, pagination.offset
    )


@router.get(
    "/notifications/unread-count",
    response_model=UnreadCountRead,
    operation_id="engagement_unread_count",
    summary="O'qilmaganlar soni",
    description="Xabarlar bo'limidagi belgi uchun.",
)
async def unread_count(user: CurrentUser, session: SessionDep) -> UnreadCountRead:
    return await NotificationService(session).unread_count(user.id)


@router.post(
    "/notifications/{notification_id}/read",
    response_model=NotificationRead,
    operation_id="engagement_mark_notification_read",
    summary="Bittasini o'qilgan deb belgilash",
    description="Allaqachon o'qilgan bildirishnoma 404 qaytaradi.",
)
async def mark_notification_read(
    user: CurrentUser, session: SessionDep, notification_id: Annotated[int, Path(ge=1)]
) -> NotificationRead:
    return await NotificationService(session).mark_read(notification_id)


@router.post(
    "/notifications/read-all",
    response_model=list[int],
    operation_id="engagement_mark_all_notifications_read",
    summary="Hammasini o'qilgan deb belgilash",
    description="O'zgargan bildirishnomalar identifikatorlarini qaytaradi.",
)
async def mark_all_read(user: CurrentUser, session: SessionDep) -> Sequence[int]:
    return await NotificationService(session).mark_all_read(user.id)
