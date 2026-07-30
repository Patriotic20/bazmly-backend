from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import Money, ReadSchema, UpdateSchema
from app.modules.menu.enums import MenuItemStatus
from app.modules.menu.schemas.menu_item_variant import MenuItemVariantRead


class MenuItemCreate(BaseModel):
    menu_category_id: int
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    base_price: Money | None = None
    currency: str = "UZS"
    photo_url: str | None = None
    has_variants: bool = False
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    sort_order: int = 0

    @model_validator(mode="after")
    def _variants_replace_the_base_price(self) -> Self:
        """Mirrors the CHECK constraint, so the 422 arrives before the 500.

        Variants replace the base price, they do not sit beside it — otherwise
        every price read has to guess which of two columns is authoritative.
        """
        if self.has_variants and self.base_price is not None:
            raise ValueError("An item with variants must not carry a base price")
        if not self.has_variants and self.base_price is None:
            raise ValueError("An item without variants needs a base price")
        return self


class MenuItemUpdate(UpdateSchema):
    menu_category_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    base_price: Money | None = None
    photo_url: str | None = None
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    sort_order: int | None = None
    is_available: bool | None = None
    status: MenuItemStatus | None = None


class BranchAvailabilityUpdate(BaseModel):
    """Konstruktorning 3-bosqichi: taomni qaysi filiallar va qanday narxda taqdim etadi.

    `venue_ids` ro'yxatiga kirmagan filialdan qator butunlay o'chiriladi — shu
    sababli taom u yerda mavjud emas holatida emas, umuman ko'rinmaydi.
    """

    venue_ids: list[int]
    price_overrides: dict[int, Money] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _overrides_belong_to_ticked_branches(self) -> Self:
        unknown = set(self.price_overrides) - set(self.venue_ids)
        if unknown:
            raise ValueError(f"Price overrides for unticked branches: {sorted(unknown)}")
        return self


class MenuItemListItem(ReadSchema):
    """Menyu katakchasi. `effective_price` filial narxi bilan hisoblangan."""

    id: int
    name: str
    photo_url: str | None = None
    effective_price: Money | None = None
    currency: str
    discount_percent: Decimal | None = None
    has_variants: bool
    is_available: bool
    status: MenuItemStatus


class MenuItemRead(ReadSchema):
    id: int
    menu_category_id: int
    name: str
    description: str | None = None
    base_price: Money | None = None
    effective_price: Money | None = None
    currency: str
    photo_url: str | None = None
    has_variants: bool
    discount_percent: Decimal | None = None
    sort_order: int
    is_available: bool
    status: MenuItemStatus
    variants: list[MenuItemVariantRead] = Field(default_factory=list)
