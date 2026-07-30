from pydantic import BaseModel, Field

from app.core.schemas import ReadSchema, UpdateSchema


class MenuCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sort_order: int = 0


class MenuCategoryUpdate(UpdateSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    sort_order: int | None = None
    is_active: bool | None = None


class MenuCategoryRead(ReadSchema):
    """`item_count` is a live COUNT, filled by the service — the chip label
    ("5" on Steyklar) is never a stored column."""

    id: int
    name: str
    sort_order: int
    is_active: bool
    item_count: int = 0
