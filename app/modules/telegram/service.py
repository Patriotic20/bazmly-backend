"""What the bot says when someone writes to it.

This is the half of Telegram that the Mini App is not. `initData` proves who
opened the app; this answers `/start` in the chat, which is where a person
actually arrives — a bot that stays silent there reads as broken no matter how
well the app behind it works.

Deliberately stateless: no database, no session. A chat message is not a domain
event here, it is a signpost pointing at the app.
"""

import json
import logging
from pathlib import Path

import httpx

from app.core.config import settings
from app.modules.telegram.schemas import TelegramUpdate

logger = logging.getLogger("app.telegram")

BOT_API = "https://api.telegram.org"

# The app's own wordmark on the brand orange, shipped with the backend rather
# than fetched from the frontend: the reply must not depend on the web app being
# reachable, and a transparent PNG would come out black once Telegram flattens it.
BANNER = Path(__file__).parent / "assets" / "start.png"

# Telegram hands back a `file_id` for every upload and accepts it in place of the
# bytes afterwards. Keyed by token so a token swap never re-sends a stale id,
# which Telegram would reject as belonging to another bot.
_banner_ids: dict[str, str] = {}

# Uzbek, like every other string a user reads.
START_TEXT = (
    "Assalomu alaykum! BAZMLY — restoran va to'yxonalarni bron qilish ilovasi.\n\n"
    "Ochish uchun pastdagi tugmani bosing."
)
HELP_TEXT = (
    "Ilovani ochish uchun pastdagi tugmani yoki menyudagi tugmani bosing.\n\n"
    "Hamkorlar uchun boshqaruv paneli: /admin\n\n"
    "Savollar bo'lsa: @bazmly_support"
)
ADMIN_TEXT = (
    "Boshqaruv paneli — bronlar, filiallar va xodimlar shu yerda.\n\n"
    "Panel faqat hamkorlar uchun: zanjir egasi bo'lmagan foydalanuvchini "
    "ilova kirish sahifasiga qaytaradi."
)
OPEN_BUTTON = "Ilovani ochish"
ADMIN_BUTTON = "Panelni ochish"


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
            text, url, button = START_TEXT, self.app_url, OPEN_BUTTON
        elif command == "/help":
            text, url, button = HELP_TEXT, self.app_url, OPEN_BUTTON
        elif command == "/admin":
            # The bot stays stateless: it does not know who owns a chain, so the
            # button is offered to everyone and the panel itself turns away
            # non-partners, exactly as it does in a browser.
            text, url, button = ADMIN_TEXT, self._admin_url, ADMIN_BUTTON
        else:
            return

        try:
            await self._send(message.chat.id, text, url=url, button=button)
        except Exception:
            logger.exception("Telegramga javob yuborib bo'lmadi: chat %s", message.chat.id)

    @property
    def _admin_url(self) -> str:
        # `app_url` may carry a path (a language prefix) or a trailing slash;
        # naive concatenation would produce `//admin`, which Next.js 404s.
        return self.app_url.rstrip("/") + "/admin"

    def _keyboard(self, url: str | None = None, button: str = OPEN_BUTTON) -> dict[str, object]:
        """The one button that opens the Mini App.

        `web_app` rather than a plain URL button: a URL opens a browser, where
        `initData` does not exist and the person would face the phone-and-password
        form instead of being signed in already.
        """
        return {"inline_keyboard": [[{"text": button, "web_app": {"url": url or self.app_url}}]]}

    async def _send(
        self, chat_id: int, text: str, *, url: str | None = None, button: str = OPEN_BUTTON
    ) -> None:
        """The logo with the text under it, or just the text if the photo fails.

        The picture is the first thing a person sees in a chat they have never
        opened before, so it carries the brand rather than a bare paragraph. It
        is not worth losing the reply over, though: anything wrong with the
        image and the words still arrive.
        """
        async with httpx.AsyncClient(timeout=10) as client:
            if await self._send_banner(client, chat_id, text, url=url, button=button):
                return
            await self._send_text(client, chat_id, text, url=url, button=button)

    async def _send_banner(
        self,
        client: httpx.AsyncClient,
        chat_id: int,
        caption: str,
        *,
        url: str | None = None,
        button: str = OPEN_BUTTON,
    ) -> bool:
        """Send the logo with the text as its caption. False if it did not go out."""
        if not BANNER.is_file():
            logger.warning("Telegram banneri topilmadi: %s", BANNER)
            return False

        data: dict[str, str] = {
            "chat_id": str(chat_id),
            "caption": caption,
            # Multipart, so the markup travels as a JSON string rather than a field tree.
            "reply_markup": json.dumps(self._keyboard(url, button)),
        }
        cached = _banner_ids.get(self.bot_token)
        if cached:
            data["photo"] = cached
            response = await client.post(f"{BOT_API}/bot{self.bot_token}/sendPhoto", data=data)
        else:
            files = {"photo": (BANNER.name, BANNER.read_bytes(), "image/png")}
            response = await client.post(
                f"{BOT_API}/bot{self.bot_token}/sendPhoto", data=data, files=files
            )

        if response.status_code != httpx.codes.OK:
            logger.warning("Telegram sendPhoto %s: %s", response.status_code, response.text[:200])
            # A cached id can go stale — drop it so the next send uploads afresh.
            _banner_ids.pop(self.bot_token, None)
            return False

        if not cached:
            self._remember_banner(response)
        return True

    def _remember_banner(self, response: httpx.Response) -> None:
        """Keep the largest size Telegram stored, so later replies send an id, not a file."""
        try:
            sizes = response.json()["result"]["photo"]
            _banner_ids[self.bot_token] = str(sizes[-1]["file_id"])
        except ValueError, KeyError, IndexError, TypeError:
            logger.warning("Telegram sendPhoto javobida file_id yo'q")

    async def _send_text(
        self,
        client: httpx.AsyncClient,
        chat_id: int,
        text: str,
        *,
        url: str | None = None,
        button: str = OPEN_BUTTON,
    ) -> None:
        payload = {"chat_id": chat_id, "text": text, "reply_markup": self._keyboard(url, button)}
        response = await client.post(f"{BOT_API}/bot{self.bot_token}/sendMessage", json=payload)
        if response.status_code != httpx.codes.OK:
            logger.warning("Telegram sendMessage %s: %s", response.status_code, response.text[:200])


def get_bot_service() -> BotService:
    return BotService(app_url=settings.telegram.app_url, bot_token=settings.telegram.bot_token)
