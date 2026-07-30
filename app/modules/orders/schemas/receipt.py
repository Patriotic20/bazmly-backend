from datetime import datetime
from typing import Any

from app.core.schemas import ReadSchema


class ReceiptRead(ReadSchema):
    """Chek bir marta yoziladi va hech qachon o'zgartirilmaydi.

    `payload` chop etilgan qatorlarni muzlatadi, shuning uchun ikki oydan keyin
    qayta chiqarilgan chek menyudagi o'zgarishlardan qat'i nazar aynan bir xil
    bo'ladi. Tuzatish — yangi buyurtma yoki pulni qaytarish, tahrir emas.
    """

    id: int
    order_id: int
    receipt_number: str
    printed_at: datetime
    fiscal_sign: str | None = None
    fiscal_serial: str | None = None
    payload: dict[str, Any]
    reprinted_count: int
