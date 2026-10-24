from pydantic import BaseModel


class MediaUploadRead(BaseModel):
    """Yuklangan rasm. `url` to'g'ridan-to'g'ri `photo_url` ga yoziladi."""

    url: str
    content_type: str
    size_bytes: int
