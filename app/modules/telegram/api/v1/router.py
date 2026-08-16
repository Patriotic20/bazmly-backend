from typing import Annotated

from fastapi import APIRouter, Header, status

from app.core.config import settings
from app.core.exceptions import PermissionDeniedError
from app.modules.telegram.schemas import TelegramUpdate, WebhookAck
from app.modules.telegram.service import get_bot_service

router = APIRouter(prefix="/v1/telegram", tags=["telegram"])


@router.post(
    "/webhook",
    response_model=WebhookAck,
    status_code=status.HTTP_200_OK,
    operation_id="telegram_webhook",
    summary="Telegram webhook",
    description=(
        "Telegram yangilanishlarni shu manzilga yuboradi. Faqat Telegram uchun: "
        "har bir so'rov `X-Telegram-Bot-Api-Secret-Token` sarlavhasi bilan "
        "tekshiriladi. Javob doim 200 — aks holda Telegram qayta yuborishni "
        "boshlaydi."
    ),
)
async def webhook(
    update: TelegramUpdate,
    secret_token: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
) -> WebhookAck:
    """The one public endpoint that is not for a browser.

    The secret header is the whole of the authentication: the URL is guessable,
    and without this anyone could post a forged update and make the bot say
    anything to any chat id they named.
    """
    expected = settings.telegram.webhook_secret
    if not expected or secret_token != expected:
        raise PermissionDeniedError("Telegram webhook tokeni noto'g'ri")

    await get_bot_service().handle(update)

    # 200 tells Telegram the update is delivered. Anything else and it retries,
    # which turns one failure into a growing backlog.
    return WebhookAck()
