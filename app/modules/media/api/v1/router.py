from typing import Annotated

from fastapi import APIRouter, File, Path, Request, Response, UploadFile, status

from app.core.dependencies import CurrentUser, SessionDep
from app.modules.media.schemas import MediaUploadRead
from app.modules.media.services import MAX_IMAGE_BYTES, MediaService

router = APIRouter(prefix="/v1/media", tags=["venue:media"])


def public_url(request: Request, path: str) -> str:
    """The absolute URL a browser on another origin can load.

    `photo_url` is rendered by the frontend, which lives on a different domain,
    so a relative path would resolve against the wrong host. Behind Railway's
    proxy the request itself arrives over plain HTTP; the forwarded headers say
    what the visitor actually used.
    """
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0]
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return f"{scheme}://{host}{path}"


@router.post(
    "/images",
    response_model=MediaUploadRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="media_upload_image",
    summary="Rasm yuklash",
    description=(
        "JPG, PNG yoki WEBP, 5 MB gacha. Qaytgan `url` taom yoki muassasa "
        "`photo_url` maydoniga yoziladi."
    ),
)
async def upload_image(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
) -> MediaUploadRead:
    # One byte over the limit is enough to refuse; reading the rest would only
    # let an oversized upload occupy memory first.
    data = await file.read(MAX_IMAGE_BYTES + 1)
    media = await MediaService(session).upload_image(user.id, data)
    return MediaUploadRead(
        url=public_url(request, request.url_for("media_get_image", key=media.key).path),
        content_type=media.content_type,
        size_bytes=media.size_bytes,
    )


@router.get(
    "/images/{key}",
    name="media_get_image",
    include_in_schema=False,
)
async def get_image(
    session: SessionDep,
    key: Annotated[str, Path(min_length=32, max_length=32, pattern="^[0-9a-f]+$")],
) -> Response:
    media = await MediaService(session).get(key)
    # A key names one upload forever — a changed photo is a new upload with a
    # new key — so the browser may keep this as long as it likes.
    return Response(
        content=media.data,
        media_type=media.content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
