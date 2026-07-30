from app.core.schemas import ReadSchema


class LanguageRead(ReadSchema):
    id: int
    code: str
    name_native: str
    name_english: str
    flag_url: str | None = None
    sort_order: int
