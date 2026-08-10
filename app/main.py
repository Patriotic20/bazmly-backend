from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.auth_mode import validate_auth_settings
from app.core.config import settings
from app.core.database.db_helper import db_helper
from app.core.handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware.logging import LoggingMiddleware
from app.core.middleware.request_id import RequestIDMiddleware
from app.core.redis import close_redis
from app.core.router import main_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    setup_logging()

    # First, because it is the guard whose failure matters most: an API that has
    # shipped with authentication off must not reach the point of opening a port.
    validate_auth_settings()

    yield

    await close_redis()
    await db_helper.dispose()


app = FastAPI(
    lifespan=lifespan,
    title="Bazmly API",
    version="1.0.0",
    summary="Restoran va to'yxonalar uchun bron va muassasa boshqaruvi.",
    description=(
        "Bu API ikki xil foydalanuvchiga xizmat qiladi. Mijoz yo'llari "
        "`/api/v1/<modul>` ostida, hodimlar yo'llari esa `/api/v1/venue/...` ostida "
        "joylashgan va ular `venue_staff` jadvalidagi ruxsat orqali tekshiriladi — "
        "tokendagi da'vo orqali emas. Shu sababli rolni o'zgartirish token muddati "
        "tugashini kutmasdan darhol kuchga kiradi.\n\n"
        "Har qanday xatolik bir xil ko'rinishda qaytariladi: `code`, `message`, "
        "`details`, `request_id`. Mijoz ilovasi doim `code` bo'yicha shart tuzishi "
        "kerak — `message` faqat ekranda ko'rsatish uchun."
    ),
    # Under the API prefix so a reverse proxy can route one path to this service.
    docs_url=f"{settings.api.prefix}/docs",
    redoc_url=f"{settings.api.prefix}/redoc",
    openapi_url=f"{settings.api.prefix}/openapi.json",
    # Declared in the order `app/core/router.py` includes them, so the Swagger
    # sections follow the module order instead of first-use order.
    openapi_tags=[
        {
            "name": "localization",
            "description": (
                "Interfeys tili ro'yxati. Kontent faqat o'zbek tilida — bu ro'yxat "
                "foydalanuvchining `users.language_id` sozlamasi uchun."
            ),
        },
        {"name": "geo", "description": "Viloyatlar va tumanlar."},
        {"name": "catalog", "description": "Muassasa turlari va qulayliklar."},
        {"name": "auth", "description": "Ro'yxatdan o'tish, kirish va token yangilash."},
        {"name": "users", "description": "Profil, qurilmalar, do'stlar va manzillar."},
        {"name": "venue:groups", "description": "Tarmoq — brend va uning filiallari."},
        {"name": "venues", "description": "Mijoz uchun muassasa qidiruvi va ma'lumoti."},
        {"name": "venue:venues", "description": "Filiallar — filial boshqaruvi."},
        {"name": "venue:staff", "description": "Hodimlar — ish joyi va taklifnomalar."},
        {"name": "venue:menu", "description": "Menyu konstruktori."},
        {"name": "services", "description": "Qo'shimcha xizmatlar katalogi va narxlari."},
        {"name": "bookings", "description": "Mijoz bronlari — Joylar bo'limi."},
        {"name": "venue:bookings", "description": "Kutilayotgan mijozlar — kunlik navbat."},
        {"name": "venue:orders", "description": "Buyurtmalar — stollardagi ochiq cheklar."},
        {"name": "reviews", "description": "Sharhlar va reyting."},
        {"name": "engagement", "description": "Sevimlilar, suhbatlar va Xabarlar."},
        {"name": "venue:analytics", "description": "Boshqaruv paneli va hisobotlar."},
    ],
)

# Middleware order as executed per request: CORS -> request id -> logging.
# Starlette runs middleware outermost-last-added, so they are added in reverse.
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors.origins,
    allow_credentials=settings.cors.allow_credentials,
    allow_methods=settings.cors.allow_methods,
    allow_headers=settings.cors.allow_headers,
    expose_headers=settings.cors.expose_headers,
)

register_exception_handlers(app)
app.include_router(main_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.run.host,
        port=settings.run.port,
        reload=settings.run.reload,
    )
