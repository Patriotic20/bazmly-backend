import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.modules.media.models import MediaFile
from app.modules.media.repositories import MediaFileRepository

MAX_IMAGE_BYTES = 5 * 1024 * 1024

# Sniffed from the bytes, never taken from the client's Content-Type: the header
# is whatever the sender typed, and these files are served back to every visitor.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


def sniff_image_type(data: bytes) -> str | None:
    for signature, content_type in _SIGNATURES:
        if data.startswith(signature):
            return content_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class MediaService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.files = MediaFileRepository(session)

    async def upload_image(self, user_id: int, data: bytes) -> MediaFile:
        if not data:
            raise ValidationFailedError("Fayl bo'sh")
        if len(data) > MAX_IMAGE_BYTES:
            raise ValidationFailedError("Rasm 5 MB dan katta bo'lmasligi kerak")
        content_type = sniff_image_type(data)
        if content_type is None:
            raise ValidationFailedError("Faqat JPG, PNG yoki WEBP rasm yuklash mumkin")

        media = await self.files.create(
            MediaFile(
                key=secrets.token_hex(16),
                content_type=content_type,
                size_bytes=len(data),
                data=data,
                uploaded_by_user_id=user_id,
            )
        )
        await self.session.commit()
        return media

    async def get(self, key: str) -> MediaFile:
        media = await self.files.get_with_data(key)
        if media is None:
            raise NotFoundError("Rasm topilmadi")
        return media
