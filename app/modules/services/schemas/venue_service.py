from pydantic import BaseModel, Field

from app.core.schemas import Money, ReadSchema, UpdateSchema
from app.modules.services.enums import ServicePriceUnit


class VenueServiceItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    price: Money
    sort_order: int = 0


class VenueServiceItemRead(ReadSchema):
    """The Taomlar rows nested under Dasturxon tuzash."""

    id: int
    name: str
    price: Money
    sort_order: int


class VenueServiceCreate(BaseModel):
    service_catalog_id: int
    price: Money
    currency: str = "UZS"
    price_unit: ServicePriceUnit = ServicePriceUnit.FLAT
    venue_id: int | None = None
    sort_order: int = 0
    items: list[VenueServiceItemCreate] = Field(default_factory=list)


class VenueServiceUpdate(UpdateSchema):
    price: Money | None = None
    price_unit: ServicePriceUnit | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class VenueServiceRead(ReadSchema):
    """`venue_id is None` means the price applies across the whole chain."""

    id: int
    venue_group_id: int
    venue_id: int | None = None
    service_catalog_id: int
    name: str
    price: Money
    currency: str
    price_unit: ServicePriceUnit
    is_active: bool
    sort_order: int
    items: list[VenueServiceItemRead] = Field(default_factory=list)
