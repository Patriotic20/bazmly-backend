from sqlalchemy import ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class MediaFile(IdIntPk, TimestampMixin, Base):
    """An uploaded image, bytes and all.

    Kept in Postgres rather than on disk: the container runs as a non-root user
    and is rebuilt on every deploy, so a file written next to the code would be
    gone by the next release. The rows travel with every database backup, and
    the API compresses nothing — the client sends an already-downscaled image.

    `key` is the public name in the URL; the integer id is never exposed, so the
    uploads cannot be walked by counting.
    """

    __tablename__ = "media_files"

    key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # Deferred so a lookup of the metadata never drags the image along.
    data: Mapped[bytes] = deferred(mapped_column(LargeBinary, nullable=False))
    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
