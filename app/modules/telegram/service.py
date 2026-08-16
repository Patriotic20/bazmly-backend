"""What the bot says when someone writes to it.

This is the half of Telegram that the Mini App is not. `initData` proves who
opened the app; this answers `/start` in the chat, which is where a person
actually arrives — a bot that stays silent there reads as broken no matter how
well the app behind it works.

Deliberately stateless: no database, no session. A chat message is not a domain
event here, it is a signpost pointing at the app.
"""

import logging

import httpx

from app.core.config import settings
from app.modules.telegram.schemas import TelegramUpdate

logger = logging.getLogger("app.telegram")

BOT_API = "https://api.telegram.org"

# Uzbek, like every other string a user reads.
START_TEXT = (
    "Assalomu alaykum! BAZMLY — restoran va to'yxonalarni bron qilish ilovasi.\n\n"
    "Ochish uchun pastdagi tugmani bosing."
)
HELP_TEXT = (
    "Ilovani ochish uchun pastdagi tugmani yoki menyudagi tugmani bosing.\n\n"
    "Savollar bo'lsa: @bazmly_support"
)
OPEN_BUTTON = "Ilovani ochish"


class BotService:
    """Answers one update. Never raises at the caller — see `handle`."""

    def __init__(self, app_url: str, bot_token: str) -> None:
        self.app_url = app_url
        self.bot_token = bot_token

    async def handle(self, update: TelegramUpdate) -> None:
        """Reply if the update is something this bot answers, else ignore it.

        Failures are logged and swallowed on purpose. Telegram reads a non-2xx
        as "not delivered" and retries with backoff, so letting an error out
        would turn one bad reply into a queue that never drains.
        """
        message = update.message
        if message is None or not message.text:
            return

        command = message.text.split()[0].split("@")[0]
        if command == "/start":
            text = START_TEXT
        elif command == "/help":
            text = HELP_TEXT
        else:
            return

        try:
            await self._send(message.chat.id, text)
        except Exception:
            logger.exception("Telegramga javob yuborib bo'lmadi: chat %s", message.chat.id)

    async def _send(self, chat_id: int, text: str) -> None:
        """A message carrying the one button that opens the Mini App.

        `web_app` rather than a plain URL button: a URL opens a browser, where
        `initData` does not exist and the person would face the phone-and-password
        form instead of being signed in already.
        """
        payload = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": {
                "inline_keyboard": [[{"text": OPEN_BUTTON, "web_app": {"url": self.app_url}}]]
            },
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{BOT_API}/bot{self.bot_token}/sendMessage", json=payload)
            if response.status_code != httpx.codes.OK:
                logger.warning(
                    "Telegram sendMessage %s: %s", response.status_code, response.text[:200]
                )


def get_bot_service() -> BotService:
    return BotService(app_url=settings.telegram.app_url, bot_token=settings.telegram.bot_token)
