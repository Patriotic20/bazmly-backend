from pydantic import BaseModel, ConfigDict


class TelegramChat(BaseModel):
    """Faqat javob yuborish uchun kerak bo'lgan qism."""

    model_config = ConfigDict(extra="ignore")

    id: int


class TelegramMessage(BaseModel):
    """Botga kelgan xabar."""

    model_config = ConfigDict(extra="ignore")

    chat: TelegramChat
    text: str | None = None


class TelegramUpdate(BaseModel):
    """Telegram webhookka yuboradigan yangilanish.

    Telegram bu yerga o'nlab turdagi yangilanish yuboradi va vaqt o'tishi bilan
    yangilarini qo'shadi, shuning uchun sxema ataylab tor: notanish maydonlar
    e'tiborsiz qoldiriladi, aks holda har bir yangi maydon 422 xatosiga
    aylanardi va Telegram yetkazishni qayta urina boshlardi.
    """

    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: TelegramMessage | None = None


class WebhookAck(BaseModel):
    """Telegram javob tanasini o'qimaydi — u faqat 200 statusini kutadi.

    Shunga qaramay bu yerda haqiqiy sxema turibdi: API dagi har bir yo'l
    `response_model` e'lon qilishi shart, va bu qoidadan istisno qilish bitta
    yo'lni hujjatsiz qoldirardi.
    """

    ok: bool = True
