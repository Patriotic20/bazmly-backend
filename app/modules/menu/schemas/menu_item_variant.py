from pydantic import BaseModel, Field

from app.core.schemas import Money, ReadSchema, UpdateSchema


class MenuItemVariantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price: Money
    sort_order: int = 0


class MenuItemVariantUpdate(UpdateSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    price: Money | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class MenuItemVariantRead(ReadSchema):
    """Kichik / O'rtacha / Katta. `effective_price` is the branch-resolved price."""

    id: int
    name: str
    price: Money
    effective_price: Money
    sort_order: int
    is_active: bool
