"""One API, two audiences, three Swagger pages.

The URL space already separates them — staff routes live under `/v1/venue/...`
with `venue:`-prefixed tags, customer routes under plain `/v1/...` — but a single
`/docs` page shows the union, and a frontend developer building one app has to
guess which half is theirs. These filters cut the one true schema into a view per
audience without touching a single path, so nothing already deployed breaks.

The tag is the routing rule: `venue:*` means the admin panel, everything else the
customer app, and `SHARED_TAGS` (sign-in, profile, reference data) appear in both
because both apps need them. Filtering happens on the *finished* schema rather
than by building two apps, so there is exactly one source of truth and the full
`/docs` keeps showing everything, telegram webhook included.
"""

from collections.abc import Callable
from copy import deepcopy
from enum import StrEnum
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

# Needed by both apps: a customer and a staff member sign in through the same
# endpoints and read the same reference data. `services` is the catalog itself —
# customers read it on a venue page, staff read it to put prices on it.
SHARED_TAGS = frozenset({"auth", "users", "geo", "catalog", "services"})

# Machine-to-machine, not for either frontend. Only the full schema shows it.
INTERNAL_TAGS = frozenset({"telegram"})

VENUE_TAG_PREFIX = "venue:"


class Audience(StrEnum):
    ADMIN = "admin"
    APP = "app"


TITLES = {
    Audience.ADMIN: "Bazmly Admin API",
    Audience.APP: "Bazmly Customer API",
}
DESCRIPTIONS = {
    Audience.ADMIN: (
        "Boshqaruv paneli uchun yo'llar — filiallar, hodimlar, menyu, bronlar "
        "navbati, buyurtmalar va hisobotlar. Hammasi `/api/v1/venue/...` ostida "
        "va `venue_staff` jadvalidagi ruxsat orqali tekshiriladi.\n\n"
        "Kirish, profil va ma'lumotnoma yo'llari ikkala hujjatda ham bor — ular "
        "umumiy. To'liq ro'yxat: `/api/docs`."
    ),
    Audience.APP: (
        "Mijoz ilovasi uchun yo'llar — qidiruv, bronlar, sharhlar, sevimlilar va "
        "xabarlar. Hodimlar yo'llari alohida hujjatda: `/api/docs/admin`.\n\n"
        "To'liq ro'yxat: `/api/docs`."
    ),
}


def _belongs(tags: list[str], audience: Audience) -> bool:
    """Whether an operation with these tags is part of this audience's view."""
    if not tags:
        # Only `/health` today. Untagged means unclassified, and hiding an
        # unclassified route from both apps is the silent kind of loss.
        return True
    for tag in tags:
        if tag in INTERNAL_TAGS:
            return False
        if tag in SHARED_TAGS:
            return True
        is_venue = tag.startswith(VENUE_TAG_PREFIX)
        if is_venue == (audience is Audience.ADMIN):
            return True
    return False


def filter_schema(full: dict[str, Any], audience: Audience) -> dict[str, Any]:
    """The full schema with only one audience's operations left in it.

    A deep copy, because FastAPI caches and hands out the original: trimming in
    place would quietly truncate `/openapi.json` for everyone after the first
    filtered request.

    `components` are left whole. Unused schemas in a reference document cost
    nothing, while pruning them means re-implementing `$ref` reachability and a
    missed edge breaks Swagger's rendering, not just its tidiness.
    """
    schema = deepcopy(full)
    schema["info"]["title"] = TITLES[audience]
    schema["info"]["description"] = DESCRIPTIONS[audience]

    paths: dict[str, dict[str, Any]] = schema.get("paths", {})
    for path, operations in list(paths.items()):
        for method, operation in list(operations.items()):
            if not _belongs(operation.get("tags", []), audience):
                del operations[method]
        if not operations:
            del paths[path]

    kept = {
        tag
        for operations in paths.values()
        for op in operations.values()
        for tag in op.get("tags", [])
    }
    schema["tags"] = [tag for tag in schema.get("tags", []) if tag["name"] in kept]
    return schema


def mount_audience_docs(app: FastAPI, prefix: str) -> None:
    """`/docs/admin` and `/docs/app` next to the full `/docs`.

    Registered as routes on the same app rather than as mounted sub-apps: a
    sub-app would re-prefix every path, and the whole point of the split is that
    no URL moves.

    The filtered schemas are cut lazily on first request and kept — `app.openapi()`
    itself is cached by FastAPI, and the route table cannot change after startup.
    """
    cache: dict[Audience, dict[str, Any]] = {}

    def schema_for(audience: Audience) -> dict[str, Any]:
        if audience not in cache:
            cache[audience] = filter_schema(app.openapi(), audience)
        return cache[audience]

    # Factories, not defs in the loop body: a closure over the loop variable
    # would leave every route serving the last audience.
    def schema_endpoint(audience: Audience) -> Callable[[], JSONResponse]:
        def endpoint() -> JSONResponse:
            return JSONResponse(schema_for(audience))

        return endpoint

    def docs_endpoint(audience: Audience) -> Callable[[], HTMLResponse]:
        def endpoint() -> HTMLResponse:
            return get_swagger_ui_html(
                openapi_url=f"{prefix}/openapi-{audience}.json",
                title=TITLES[audience],
            )

        return endpoint

    for audience in Audience:
        app.add_api_route(
            f"{prefix}/openapi-{audience}.json",
            schema_endpoint(audience),
            include_in_schema=False,
        )
        app.add_api_route(
            f"{prefix}/docs/{audience}",
            docs_endpoint(audience),
            include_in_schema=False,
        )
