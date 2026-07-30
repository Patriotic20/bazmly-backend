from pydantic import BaseModel, Field

from app.core.schemas import Money, ReadSchema


class BookingItemCreate(BaseModel):
    menu_item_id: int
    quantity: int = Field(gt=0)


class BookingItemRead(ReadSchema):
    """`name_snapshot` va `unit_price` tasdiqlash paytida saqlab qolinadi.

    Eski chekni jonli `menu_items` bilan qayta qurish mumkin emas — narx va nom
    o'zgaradi, chek esa kelishilgan qiymatni ko'rsatib turishi kerak.
    """

    id: int
    menu_item_id: int
    quantity: int
    unit_price: Money
    total_price: Money
    name_snapshot: str
