Ready for review
Select text to add comments on the plan
Bazmly Backend — Audit natijalari va tuzatish rejasi
Kontekst
/home/bekzop/Project/baz — FastAPI backend (15 modul, 105 endpoint, 417 Python fayl). Ish daraxtida 141 fayllik commit qilinmagan "translations collapse" refaktoringi bor (ko‘p tilli *_translation jadvallari o‘chirilgan, kontent endi faqat o‘zbekcha).

Uchta agent butun backendni tekshirdi: core qatlami, auth/venues/catalog/menu modullari, bookings/orders/testlar. Natija: 50+ ta haqiqiy muammo, jumladan 5 ta kritik xavfsizlik teshigi va 2 ta butunlay ishlamaydigan asosiy oqim. Har bir topilma kod o‘qib tasdiqlangan — taxmin yo‘q; eng muhimlari shaxsan qayta tekshirildi.

Bugun avvalroq 4 ta xato allaqachon tuzatilgan (qayta sanalmaydi): 3 ta Python-2 except A, B: sintaksis xatosi va venue_repository.get_detail dagi IndexError.

Foydalanuvchi qarorlari:

Reja hajmi: hammasi, 5 bosqichda
Social login: endpoint o‘chiriladi (JWKS keyinroq, kerak bo‘lganda)
Vaqt zonasi: bazada UTC+0 saqlanadi, Pydantic qatlamida +5 (Asia/Tashkent) ga o‘giriladi
Umumiy holat
Sog‘lom tomonlari (tegilmasin): pul hisob-kitobi (Decimal, Numeric(14,2), ROUND_HALF_UP, float aralashmasi yo‘q); tranzaksiya intizomi (repozitoriylarda birorta commit() yo‘q); DB darajasidagi konkurentlik himoyasi (no_overlapping_table_bookings, one_open_order_per_table, SELECT … FOR UPDATE); soft-delete filtrlari to‘liq; PostGIS ST_DWithin metrlarda to‘g‘ri; migratsiya zanjiri bitta chiziqli head (4f2ba1c07d9e), model/migratsiya parity 11 jadval 16 ustunda aniq; 57 model / 57 jadval / 57 __all__ mos; barcha 16 router ulangan; ruff va mypy --strict toza; import app.main ishlaydi. Python tomonda translations collapse to‘liq tugagan — grep -r "_translation" app tests hech nima qaytarmaydi.

Testlar: uv run pytest → 32 xato. Sabab kodda emas — .env dagi AUTH_MODE=disabled. APP_CONFIG__SECURITY__AUTH_MODE=enforced bilan → 246 passed, 1 xfailed (shaxsan tekshirildi). Yashirin xavf: auth_disabled() holatida PermissionRequired erta qaytadi, ya’ni ijobiy ruxsat testlari hech nimani tekshirmay o‘tib ketadi — haqiqiy avtorizatsiya regressiyasi sezilmay chiqib ketishi mumkin.

Bosqich 1 (P0) — Xavfsizlik
Bu bosqich tugamaguncha tizim ochiq internetga chiqarilmasin.

1.1 Kritik
#	Fayl	Muammo	Yechim
1	core/config.py:47-54,124 + .env.template:41	JWT kaliti repoda ochiq. SecurityConfig docstring’i "non-local muhitda ishga tushishda rad etiladi" deydi — bunday tekshiruv yo‘q. .env.template esa faol config manbai (env_file=(".env.template", ".env")) va ichida dev-only-change-me-32-bytes-min!! yozilgan. Tasdiqlandi: hozirgi fayllar bilan Settings().security.secret_key aynan shu default. Env unutilsa — istalgan odam istalgan user_id uchun token yasaydi	validate_auth_settings() ga fatal tekshiruv: non-local muhitda default kalit yoki 32 baytdan qisqa kalit → ishga tushmasin. .env.template ni env_file dan olib tashlash (faqat hujjat bo‘lib qolsin)
2	auth/services/auth_service.py:195-206	[BAJARILDI]	Apple olib tashlandi; Google endi id_token ni Google JWKS orqali tekshiradi (app/core/integrations/google/). Email bo‘yicha bog‘lash faqat email_verified=true da. auth_identities jadvali qoldi
3	staff/repositories/venue_staff_repository.py:84	Kompaniyalararo ruxsat. or_(venue_id == X, venue_id.is_(None)) — guruh darajasidagi qator (har bir egasida shunday) istalgan kompaniyaning istalgan filialida ruxsat beradi. Bu 12 ta require_permission_in_transaction chaqiruvining tayanchi	Venue ga join + venue_id IS NULL shoxiga VenueStaff.venue_group_id == Venue.venue_group_id sharti
4	staff/services/staff_service.py:170-177	Ruxsat tekshiruvi butunlay o‘tkazib yuboriladi. Yangi kompaniyada filial darajasidagi qator bo‘lmaydi → guard_venue = None → if ishlamaydi. Istalgan foydalanuvchi begona kompaniyaga xodim taklif qiladi	Blok o‘rniga mavjud require_group_permission_in_transaction(actor_user_id, group_id, PERM_STAFF_MANAGE) (staff_service.py:84)
5	orders/api/v1/router.py:189-193	Chek IDOR. get_receipt da ruxsat ham, venue_id ham, scoping ham yo‘q; order_id ketma-ket son. Platformadagi har bir muassasaning to‘liq hisob-kitobi ochiq	venue_id: Query + dependencies=[require_permission("orders.view")], lookup’ni venue bo‘yicha cheklash
1.2 Yuqori — IDOR va himoyasiz endpointlar
#	Fayl	Muammo	Yechim
6	orders/api/v1/router.py:40,56,71,104	table_board, kitchen_queue, list_orders, get_detail — guard yo‘q. Raqobatchining jonli stol taxtasi va ochiq cheklari ko‘rinadi (shu routerdagi yozish amallari yaqinda himoyalangan, o‘qishlar unutilgan)	To‘rttasiga require_permission("orders.view")
7	bookings/api/v1/venue.py:30-36,79-87	list_day va blocked_dates himoyasiz. BookingRead ichida contact_name+contact_phone → istalgan muassasaning mehmonlar telefon daftari ochiladi	require_permission("bookings.view")
9	engagement/services/notification_service.py:102	mark_read(notification_id) da user_id yo‘q → begona xabarni o‘qish va "o‘qilgan" qilish	mark_read(user_id, notification_id) + WHERE ga user_id
10	engagement/services/conversation_service.py:69,75	history() va mark_read() egalikni tekshirmaydi (send() esa 60-62-qatorda tekshiradi)	send() dagi tekshiruvni ikkalasiga qo‘shish
11	services/…/venue_service_catalog_service.py:73-89	Ruxsat bitta venue’da, yozuv boshqasiga (payload.venue_id) ketadi → begona muassasaga pullik xizmat qo‘shish	Himoyalangan venue_id ni ishlatish + venue.venue_group_id == group_id
12	analytics/api/v1/router.py:26-34	Venue darajasidagi guard, guruh darajasidagi ma’lumot → begona kompaniyaning oylik daromadi	require_group_permission("reports.view") (core/dependencies.py:289)
13	staff/services/staff_service.py:283	Ruxsat venue_id da, set_active faqat staff_id bo‘yicha yangilaydi → begona kompaniya xodimini o‘chirish	Qatorni yuklab zanjir mosligini tekshirish
14	venue_groups/api/v1/router.py:70-75	update_group guard venue_id ni o‘qiydi, yozuv group_id ga ketadi	require_group_permission("settings.edit")
15	menu/services/menu_service.py:188-197	set_branch_availability ixtiyoriy venue_ids ga yozadi, zanjir tekshirilmaydi. Route menu.publish, servis menu.edit — ikki xil slug	Guruh bo‘yicha ruxsat + har bir venue_id ni tekshirish + slugni birxillashtirish
16	10 ta endpoint	Xodim endpointlarida guard yo‘q: list_staff (PII sizadi), staff_counts, list_branches, status_counts, get_branch, get_with_branches, list_categories, list_items, get_item	Har biriga mos require_permission / require_group_permission
17	auth/services/auth_service.py:242-246	[BAJARILDI]	/auth/logout endi body’da refresh token oladi va aynan o‘shani bekor qiladi; logout_all alohida metod
18	auth/schemas/auth.py:8,14	[BAJARILDI]	Barcha auth sxemalari PhoneNumber tipidan foydalanadi; uch xil format bitta akkauntga tushishi test bilan qopdi
19	auth/services/auth_service.py:231	[BAJARILDI]	refresh, login va google_login endi _require_usable orqali bloklangan/o‘chirilgan akkauntni rad etadi
20	core/config.py:27-31 + main.py:101-107	origins=["*"] + allow_credentials=True. Bajarib tasdiqlandi: Starlette wildcard’ni "so‘ragan origin’ni qaytar" ga aylantiradi — Origin: https://evil.example javobda allow-origin: https://evil.example + allow-credentials: true oladi	Default origins=[]; non-local muhitda "*" + credentials → fatal xato

Bosqich 2 (P1) — Ishlamayotgan asosiy funksiyalar
#	Fayl	Muammo	Yechim
23	bookings/ (butun modul)	Hech qanday bron confirmed bo‘lmaydi. set_status ning yagona chaqiruvchisi cancel va u doim CANCELLED beradi; tasdiqlash endpointi yo‘q. Natija: QR check-in doim 422; expire_stale hech nima topmaydi; check_out erishib bo‘lmas. Bronlar abadiy pending	POST /v1/venue/bookings/{id}/confirm + require_permission("bookings.confirm")
25	menu/services/menu_service.py:172	Taom yaratish doim 404. create_item MenuItemBranch qatori yaratmaydi, get_item esa unga inner join qiladi. Ob’yekt saqlanadi, javob xato	Commit’dan oldin MenuItemBranch yaratish yoki javobni yangi ob’yektlardan qurish
26	core/dependencies.py:161-164	get_current_user_optional faqat 2 xatoni ushlaydi; NotFoundError (o‘chirilgan foydalanuvchi tokeni) o‘tib ketadi → ochiq GET /v1/venues/search 404 qaytaradi	except ga NotFoundError qo‘shish
27	venues/services/venue_service.py:107	name=vt.slug — chala tahrir. Foydalanuvchi Restoran o‘rniga restoran ko‘radi (qo‘shni amenity shoxi to‘g‘ri)	name=vt.name. Shu xato services/…/venue_service_catalog_service.py:115 da ham
28	alembic/…b7834c92fef5_seed_reference_data.py:138	Amenity seed’i tarjima yozmagan → collapse migratsiyasining name = slug fallback’i ishlagan. GET /v1/amenities parking, wifi, air_conditioning qaytaradi	Yangi data-migratsiya: 6 ta amenity’ga o‘zbekcha nom
29	bookings/services/booking_service.py:173,241,573	Tasdiqlash SMS’i bo‘sh muassasa nomi bilan ketadi (venue_name=None → "")	_detail_in_transaction(created, venue_name=venue.name)
30	bookings/services/booking_service.py:451	Chek qatorida xizmat nomi o‘rniga #7 — collapse qoldig‘i	ServiceCatalog ga join, catalog.name ni snapshot qilish
31	reviews/	Sharhlar PENDING yaratiladi, publish hech qayerdan chaqirilmaydi → sharhlar ro‘yxati abadiy bo‘sh, rating_avg qimirlamaydi	Moderatsiya endpointi (publish), admin ruxsati ostida
32	butun loyiha	Scheduler yo‘q. expire_stale (bronlar), taklif muddati, SMS qayta yuborish — hech qachon chaqirilmaydi	arq worker (mavjud TODO(queue) izohlariga mos) yoki vaqtincha admin-trigger
Bosqich 3 (P2) — Vaqt zonasi
Yondashuv: bazada hamma vaqt belgisi UTC+0 (hozirgidek utcnow_naive()), Pydantic javob sxemalarida +5 (Asia/Tashkent) ga o‘giriladi. Ichki solishtirishlar uchun bitta markaziy yordamchi.

app/core/time.py (yangi): TASHKENT = ZoneInfo("Asia/Tashkent"), now_local() (UTC → +5, naive), to_utc(local_dt), to_local(utc_dt).
app/core/schemas.py ga LocalDateTime annotatsiyasi — field_serializer orqali UTC → +5. Javob sxemalaridagi vaqt maydonlari shunga o‘tkaziladi (created_at, confirmed_at, checked_in_at, sent_at, expires_at, …).
Solishtirishlarni tuzatish:
#	Fayl	Muammo
33	venues/services/venue_service.py:43,82	local_dt or utcnow_naive() → is_open_now 5 soat xato: 10:00–23:00 ishlaydigan joy mahalliy 15:00 gacha "yopiq" va only_open_now filtridan tushib qoladi → now_local()
34	bookings/services/booking_service.py:396,402	auto_cancel_at mahalliy vaqtdan hisoblanib UTC ustunga yoziladi va utcnow_naive() bilan solishtiriladi → no-show 5 soat erta; depozit qaytarish oynasi ham xato → to_utc()
35	orders/services/order_service.py:77,89	Biznes kuni mahalliy 06:00 emas, 11:00 da almashadi → next_order_number va venue_daily_stats buziladi → now_local()
36	bookings/services/booking_service.py:373-381	Lead-time butun kunlar bilan: bugungi o‘tib ketgan soatga bron qilish mumkin; 00:00–05:00 da bir kunga xato → now_local() + days_ahead == 0 da start_time > now.time()
Bosqich 4 (P3) — Mantiq va ma’lumot yaxlitligi
#	Fayl	Muammo	Yechim
38	bookings/services/booking_service.py:441-463	Bron xizmatlari muassasaga bog‘lanmaydi → begona kompaniyaning arzon xizmatini qimmat to‘yxona broniga ulash mumkin (yonidagi _build_items_in_transaction to‘g‘ri qiladi)	venue_id/venue_group_id ni uzatib mos kelmaganini rad etish
39	bookings/services/booking_service.py:452	price_unit (flat/per_guest/per_hour) e’tiborsiz — per_guest xizmat mijoz yuborgan quantity bo‘yicha hisoblanadi	price_unit bo‘yicha shoxlanish
40	bookings/services/booking_service.py:391	_staff_works_at da row.venue_id in (venue_id, None) — None doim rost → begona zanjirda check-in	Guruh bo‘yicha solishtirish
41	bookings/api/v1/venue.py:48-55	Check-in guard venue_id ni query’dan, amal esa body’dan oladi → yo 422, yo boshqa muassasada tekshirilgan ruxsat	venue_id ni body’dan olib Query/Path ga o‘tkazish
43	bookings/schemas/booking.py:55	HallEventCreate.venue_service_ids hech qayerda o‘qilmaydi — mijoz to‘ldirsa jimgina yo‘qoladi	Maydonni o‘chirish yoki ulash
44	engagement/services/favorite_service.py:28-34	Tekshir-keyin-qo‘sh poygasi → ikki marta bosishda 409 (idempotent deb hujjatlashtirilgan)	ON CONFLICT DO NOTHING + rowcount
45	core/middleware/request_id.py:30 + handlers.py:158	500 javoblarda request_id doim "-" va X-Request-ID header yo‘q (Exception handleri RequestIDMiddleware dan tashqarida ishlaydi). README:139 har javobda header va’da qiladi. Eng kerakli xato turida aynan id yo‘qoladi	request.state.request_id dan o‘qish yoki middleware’ni tashqariga chiqarish
46	core/integrations/sms/eskiz/token.py:128	Redis LockError SmsError taksonomiyasidan chetda → OTP endpoint 502 o‘rniga 500 qaytaradi (mobil mijoz 502 ni qayta urishga mo‘ljallangan)	Lock olishni o‘rab SmsTransportError qilib qayta ko‘tarish
47	staff/repositories/venue_staff_repository.py:47	get_for_user_and_venue da is_active filtri yo‘q → o‘chirilgan xodim buyurtmaga biriktiriladi	Filtr qo‘shish
48	staff/services/staff_service.py:123	Faol bo‘lmagan roldagi xodim role_name="" bilan chiqadi	Barcha rollarni olish yoki fallback
Bosqich 5 (P4) — Tozalash, hujjat, infratuzilma
#	Fayl	Muammo	Yechim
49	catalog/repositories/__init__.py:6	__all__ da o‘chirilgan AmenityRow/VenueTypeRow → ImportError (ruff __init__.py ichida F822 ni ushlamaydi)	Ikkalasini olib tashlash
50	tests/conftest.py	.env dagi AUTH_MODE=disabled sababli 32 test yiqiladi va ijobiy ruxsat testlari bo‘sh joyda o‘tadi	Session-scoped autouse fixture: auth_mode = ENFORCED (test_auth_mode_* fayllari aniq opt-out qiladi)
51	tests/	has_permission uchun kompaniyalararo test yo‘q (has_group_permission da bor)	§3 tuzatilgach regressiya testi
52	O‘lik kod	core/dependencies.py:170-201 (get_language_id/LanguageId, nol chaqiruv, lekin DB so‘rovi qiladi), :346 (venue_id_path), core/pagination.py:9-19,36-58 (PaginationParams, paginate() — chaqiruvchi yo‘q), core/exceptions.py:30-51 (4 ta hech qachon ko‘tarilmaydigan sinf), menu/services/menu_service.py:42 (LanguageRepository), catalog/repositories/amenity_repository.py:31-39, venues/services/venue_service.py:83-89 (no-op model_copy)	O‘chirish
53	alembic/…73548a20054d_collapse…py:168	Ishlatilmagan cols; downgrade() trigram indekslarni tiklamaydi → to‘liq downgrade zanjiri yiqiladi	Lokalni o‘chirish, downgrade’ga indekslarni qo‘shish
54	alembic/…4f2ba1c07d9e_seed_role_permissions.py:104	ON CONFLICT DO NOTHING yo‘q → qo‘lda grant qilingan bazada upgrade head yiqiladi	Qo‘shish
55	core/security.py:108	decode_access_token exp ni majburiy qilmaydi → exp siz token abadiy yashaydi	options={"require": ["exp", "sub", "type"]}
57	docker/entrypoint.sh:4	Har konteyner alembic upgrade head qiladi → ko‘p replikada DDL poygasi; backend da healthcheck yo‘q	Migratsiyani bir martalik init-job ga (yoki advisory lock) ko‘chirish + healthcheck
58	notifications/api/	Router bo‘sh va (to‘g‘ri) ulanmagan — butun api/ shoxi o‘lik sim	O‘chirish yoki mo‘ljallangan admin route’larni qo‘shish
59	services/…/venue_service_catalog_service.py:53-55	N+1 (har xizmat uchun alohida so‘rov)	WHERE venue_service_id IN (:ids) — ReviewRepository.list_for_venue namunasi bor
60	Hujjatlar	API_PLAN.md:145,203 hali /v1/subscriptions/* ni sanaydi (jonli OpenAPI bilan yagona farq); MODEL_PLAN.md (8), SCHEMA_PLAN.md (2), REPOSITORY_PLAN.md (1), SERVICE_PLAN.md (1), CONVENTIONS.md, DECISIONS.md hali *_translation jadvallarini tasvirlaydi; README.md:97,101,112,121,139 da mavjud bo‘lmagan modul, boshqa loyihadan qolgan matn, noto‘g‘ri yo‘l va /api/health haqida noto‘g‘ri va’da; sms/eskiz/*.py mavjud bo‘lmagan SMS_PLAN.md ga ishora qiladi	Hammasini joriy holatga keltirish
Bajarish tartibi va asosiy fayllar
Bosqich 1 (P0) — xavfsizlik, har tuzatishga regressiya testi
Bosqich 2 (P1) — bron tasdiqlash → check-in → check-out oqimini tiklash
Bosqich 3 (P2) — core/time.py + Pydantic serializer, keyin 4 solishtiruv
Bosqich 4 (P3) — mantiq va poygalar
Bosqich 5 (P4) — tozalash, hujjat, infratuzilma
Har bosqich alohida commit(lar) bilan yakunlanadi.

Eng ko‘p tegiladigan fayllar:

app/modules/staff/repositories/venue_staff_repository.py — butun avtorizatsiyaning tayanchi (§3)
app/modules/staff/services/staff_service.py — §4, §13, §48
app/modules/bookings/services/booking_service.py — eng ko‘p topilma (§23, 29, 30, 34, 36, 38-40)
app/modules/orders/api/v1/router.py — §5, §6
app/modules/auth/services/auth_service.py — §2, §17, §19
app/core/config.py — §1, §20
app/core/dependencies.py — require_permission / require_group_permission (qayta ishlatiladi), §26
app/core/time.py — yangi, vaqt zonasi markazi
Tekshirish
Har bosqichdan keyin:

APP_CONFIG__SECURITY__AUTH_MODE=enforced uv run pytest -q   # hozirgi holat: 246 passed, 1 xfailed
uv run ruff check app && uv run mypy --strict app
Bosqich 1:

Ikkita kompaniya + ikkita egasi seed qilinadi. A egasining tokeni bilan B ning venue_id/group_id siga murojaat → hamma joyda 403 (hozir bir nechtasi 200)
POST /v1/auth/social/google → 404/405 (o‘chirilgan)
GET /v1/venue/orders/{id}/receipt begona muassasa uchun → 403
logout dan keyin eski refresh token bilan /refresh → 401
Non-local ENV + default secret_key → ilova ishga tushmasin
Bosqich 2: to‘liq oqim — bron yaratish → confirm → QR check-in → check-out, har qadam 200 (hozir confirm yo‘q, check-in 422). GET /v1/amenities o‘zbekcha nom qaytarsin. POST /v1/venue/menu/items 201 qaytarsin (hozir 404).

Bosqich 3: GET /v1/venues/search?only_open_now=true mahalliy ish vaqtida muassasani qaytarsin; javobdagi created_at +5 da kelsin.

Umumiy: docker compose up -d --build → GET /api/health → {"status":"ok"}. Diqqat: .env da hozir AUTH_MODE=disabled — ishlab chiqarish uchun enforced shart.