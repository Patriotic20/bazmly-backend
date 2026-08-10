# Bazmly — Database Schema

Reference document for the backend. Derived from the Figma screens (customer app + venue-owner onboarding).

**Stack:** PostgreSQL, SQLAlchemy 2.0 async, Alembic
**Extensions required:** `postgis`, `btree_gist`, `pg_trgm`
**Conventions:** integer PKs, `created_at` / `updated_at` as naive UTC (`TIMESTAMP WITHOUT TIME ZONE`), money as `Numeric(14,2)` + explicit currency column (default `UZS`)

---

## Table of contents

1. [auth](#1-auth)
2. [localization](#2-localization)
3. [geo](#3-geo)
4. [catalog](#4-catalog)
5. [venues](#5-venues)
6. [menu](#6-menu)
7. [catering](#7-catering)
8. [bookings](#8-bookings)
9. [subscriptions](#9-subscriptions)
10. [reviews](#10-reviews)
11. [engagement](#11-engagement)
12. [Design decisions](#design-decisions)
13. [Constraints and indexes](#constraints-and-indexes)
14. [Migration order](#migration-order)
15. [Open questions](#open-questions)

---

## 1. auth

### users
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| first_name | varchar(100) | |
| last_name | varchar(100) | |
| phone | varchar(20) unique null | E.164 |
| email | varchar(255) unique null | |
| avatar_url | text null | |
| language_id | FK languages | |
| district_id | FK districts null | profile "Manzil" |
| role | enum | customer, venue_owner, venue_staff, moderator, admin |
| status | enum | pending_profile, active, blocked, deleted |
| phone_verified_at | timestamp null | |
| email_verified_at | timestamp null | |
| last_login_at | timestamp null | |
| deleted_at | timestamp null | soft delete |

`CHECK (phone IS NOT NULL OR email IS NOT NULL)` — social login gives no phone, phone login gives no email.

### auth_identities
`id`, `user_id` FK, `provider` enum(apple, google), `provider_user_id` varchar, `provider_email` varchar null, `raw_profile` jsonb

`UNIQUE (provider, provider_user_id)` — one row per linked social account; a user may link both.

### verification_codes
`id`, `user_id` FK null, `channel` enum(sms, email), `destination` varchar, `code_hash` varchar, `purpose` enum(registration, login, phone_change, email_change, card_binding), `attempts_count` int, `expires_at`, `consumed_at` null, `request_ip` inet

Store the hash, never the code. `destination` is denormalized because at registration there is no user row yet. The same table serves the card-binding OTP.

### refresh_tokens
`id`, `user_id` FK, `device_id` FK null, `token_hash`, `expires_at`, `revoked_at` null, `ip` inet, `user_agent` text

### devices
`id`, `user_id` FK, `platform` enum(ios, android), `device_uuid` varchar, `push_token` text null, `app_version` varchar, `last_seen_at`

`UNIQUE (user_id, device_uuid)`

### friendships
`id`, `requester_id` FK users, `addressee_id` FK users, `status` enum(pending, accepted, blocked)

`UNIQUE (requester_id, addressee_id)`, `CHECK (requester_id <> addressee_id)` — backs the "Add friends" button on the profile screen.

---

## 2. localization

### languages
`id`, `code` varchar(5) unique, `name_native`, `name_english`, `flag_url`, `is_active` bool, `sort_order` int

Seed: `uz`, `en`, `ru` — the "Til sozlamalari" screen offers exactly these three.

---

## 3. geo

### regions
`id`, `name`, `code` — viloyat (Toshkent, Navoiy, Samarqand, Buxoro, …)

### districts
`id`, `region_id` FK, `name`, `latitude`, `longitude`

Holds both *tuman* and *shahar* rows (Yashnobod tumani, Olmazor tumani, Toshkent shahri). The Figma labels this level "Shahar" on the owner form and "Tuman" on the customer form — same level, one table. Pick one label for the API and keep it consistent.

### user_recent_locations
`id`, `user_id` FK, `district_id` FK, `label`, `latitude`, `longitude`, `last_used_at`

Backs "Oxirgi manzillar". Cap at ~10 rows per user, evict oldest.

---

## 4. catalog

### venue_types
`id`, `slug` unique (restoran, toyxona, kafe), `icon_url`, `sort_order`, `is_active`

### venue_type_translations
`id`, `venue_type_id` FK, `language_id` FK, `name` — `UNIQUE (venue_type_id, language_id)`

### amenities
`id`, `slug`, `icon_url`, `sort_order` — parking, sound system, stage, air conditioning, professional kitchen, Wi-Fi

### amenity_translations
`id`, `amenity_id` FK, `language_id` FK, `name` — `UNIQUE (amenity_id, language_id)`

---

## 5. venues

### venues
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| owner_id | FK users | |
| district_id | FK districts | |
| street | varchar | Ko'cha |
| house_number | varchar | Uy |
| latitude / longitude | numeric | from map pin |
| location | geography(Point,4326) | GiST indexed |
| phone | varchar(20) | |
| logo_url | text null | 500×500, used for map markers |
| total_seats | int null | "umumiy joylar soni" |
| capacity_min / capacity_max | int null | to'yxona range, e.g. 500–1200 |
| base_price | numeric null | headline price |
| currency | char(3) | default UZS |
| min_advance_booking_days | smallint | 1 / 2 / 3 |
| late_grace_minutes | smallint | default 40 |
| requires_deposit | bool | |
| deposit_percent | numeric(5,2) null | |
| discount_percent | numeric(5,2) null | "10% chegirma" badge |
| rating_avg | numeric(2,1) | denormalized |
| reviews_count | int | denormalized |
| status | enum | draft, pending, active, blocked |
| onboarded_at | timestamp null | "Restaurant is live" |

### venue_venue_types
`venue_id` FK, `venue_type_id` FK — **many-to-many**. The owner form's "Faoliyat turini tanlang" allows Restoran + To'yxona + Barchasi, so a venue can be both. "Barchasi" is a UI shortcut that inserts every type, not a type row of its own.

### venue_translations
`id`, `venue_id` FK, `language_id` FK, `name`, `description` (Tavsif) — `UNIQUE (venue_id, language_id)`

### venue_photos
`id`, `venue_id` FK, `url`, `sort_order`, `is_cover` — max 10 per venue, enforced in the service

### venue_working_hours
`id`, `venue_id` FK, `weekday` smallint (0–6), `opens_at` time, `closes_at` time, `is_closed` bool

Owner onboarding collects one start/end time plus a set of weekdays, which writes 7 rows. Drives the "Ochiq" badge.

### venue_special_days
`id`, `venue_id` FK, `date`, `is_closed`, `opens_at` null, `closes_at` null — holidays, overrides working hours

### venue_amenities
`venue_id` FK, `amenity_id` FK — M2M

### venue_staff
`id`, `venue_id` FK, `user_id` FK, `role` enum(owner, manager, waiter), `is_active`

Who may confirm bookings and scan customer tickets.

### venue_tables
`id`, `venue_id` FK, `number` int, `seats` smallint, `zone` enum(indoor, terrace, vip) null, `is_active`

`UNIQUE (venue_id, number)`. Restaurants only.

> Onboarding collects **counts per capacity bucket** (2 / 4 / 6 / 8 / 10+ kishilik stollar soni), but booking shows **numbered tables** (Joyni belgilash: 1…7). So generate individual rows from the counts at onboarding — e.g. 3 four-seat tables becomes three rows numbered sequentially. Do not store the buckets; they are input, not state.

### venue_table_qrs
`id`, `table_id` FK, `token` varchar unique, `printed_at`, `revoked_at` null

The printed standee the customer scans with the center nav button.

### venue_guest_tiers
`id`, `venue_id` FK, `min_guests`, `max_guests` null, `base_price` numeric, `sort_order`

To'yxona only: 100–150 / 150–200 / 200–300 / 300+ with a base price each.

---

## 6. menu

Restaurants.

### menu_categories
`id`, `venue_id` FK, `sort_order`, `is_active`
### menu_category_translations
`id`, `menu_category_id` FK, `language_id` FK, `name`
### menu_items
`id`, `menu_category_id` FK, `price` numeric, `currency`, `photo_url`, `is_available`, `sort_order`
### menu_item_translations
`id`, `menu_item_id` FK, `language_id` FK, `name`, `description`

---

## 7. catering

To'yxona "dasturxon" packages.

### catering_packages
`id`, `venue_id` FK, `code` enum(self_service, standard, premium), `price_per_guest` numeric, `is_self_service` bool, `is_active`

"O'zimiz tayyorlaymiz" is a row with `is_self_service = true` and `price_per_guest = 0`.

### catering_package_translations
`id`, `package_id` FK, `language_id` FK, `name`, `description`

### catering_sections
`id`, `package_id` FK, `icon`, `sort_order`
### catering_section_translations
`id`, `section_id` FK, `language_id` FK, `title`, `contents`

Sections match the "Menyu tarkibi" list: Salatlar, Mevalar, Asosiy taomlar, Ichimliklar, Shirinliklar.

---

## 8. bookings

### bookings

One table, two kinds. Shared columns first:

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| user_id | FK users | |
| venue_id | FK venues | |
| kind | enum | table_reservation, hall_event |
| booking_date | date | **local venue date, no UTC conversion** |
| start_time | time | local |
| end_time | time | local |
| guests_count | int | |
| status | enum | pending, confirmed, checked_in, completed, cancelled, no_show, expired |
| contact_name | varchar | |
| contact_phone | varchar(20) | |
| note | text null | |
| subtotal | numeric | |
| deposit_amount | numeric | |
| deposit_paid_at | timestamp null | |
| total_amount | numeric | |
| currency | char(3) | |
| receipt_number | varchar unique | "Chek raqami" |
| ticket_code | varchar(16) unique | human fallback |
| qr_token | varchar(32) unique | shown to the venue |
| auto_cancel_at | timestamp null | start + late_grace_minutes |
| confirmed_at | timestamp null | |
| checked_in_at | timestamp null | set on QR scan |
| checked_out_at | timestamp null | |
| seated_minutes | int null | written once at completion |
| cancelled_at | timestamp null | |
| cancel_reason | text null | |
| completed_at | timestamp null | |

Kind-specific:

| Column | Applies to |
|---|---|
| table_id FK venue_tables | table_reservation |
| reserved_range tstzrange (generated) | table_reservation |
| guest_tier_id FK venue_guest_tiers | hall_event |
| catering_package_id FK catering_packages | hall_event |

`CHECK`: `kind = 'table_reservation'` → `table_id IS NOT NULL AND guest_tier_id IS NULL`; `kind = 'hall_event'` → `guest_tier_id IS NOT NULL AND table_id IS NULL`.

### booking_items
`id`, `booking_id` FK, `menu_item_id` FK, `quantity`, `unit_price`, `total_price`, `name_snapshot`

Restaurant menu pre-order (the Menu step of the wizard).

### booking_price_lines
`id`, `booking_id` FK, `sort_order`, `line_type` enum(hall_rental, catering, service_logistics, deposit), `label_snapshot`, `unit_price`, `quantity`, `amount`

Backs the "Detailed Price Report". Frozen at confirmation.

### booking_status_history
`id`, `booking_id` FK, `from_status`, `to_status`, `changed_by_user_id` FK null, `comment`

### venue_blocked_slots
`id`, `venue_id` FK, `table_id` FK null, `date`, `start_time`, `end_time`, `reason` enum(manual, maintenance, private_event)

---

## 9. subscriptions

### subscription_plans
`id`, `code` enum(monthly, yearly), `price`, `currency`, `duration_days`, `benefit_percent`, `is_active`, `sort_order`
### subscription_plan_translations
`id`, `plan_id` FK, `language_id` FK, `name`, `description`
### user_subscriptions
`id`, `user_id` FK, `plan_id` FK, `status` enum(active, past_due, cancelled, expired), `started_at`, `current_period_start`, `current_period_end`, `next_payment_at`, `auto_renew`, `cancelled_at` null

---

## 10. reviews

### reviews
`id`, `user_id` FK, `venue_id` FK, `booking_id` FK unique null, `rating` smallint (1–5), `comment` text, `is_verified` bool, `status` enum(pending, published, rejected), `published_at`

The "Verified" badge means `booking_id IS NOT NULL`. The unique constraint gives one review per completed booking.

### review_photos
`id`, `review_id` FK, `url`, `sort_order`

### review_replies
`id`, `review_id` FK, `venue_id` FK, `author_user_id` FK, `body`

---

## 11. engagement

### favorites
`id`, `user_id` FK, `venue_id` FK — `UNIQUE (user_id, venue_id)`, the bookmark icon

### search_history
`id`, `user_id` FK, `query`, `filters` jsonb

### conversations
`id`, `user_id` FK, `venue_id` FK, `booking_id` FK null, `last_message_at`
### messages
`id`, `conversation_id` FK, `sender_type` enum(user, venue), `sender_user_id` FK, `body`, `read_at` null

Backs "Xabar yuborish" on the active-booking card.

### notifications
`id`, `user_id` FK, `type`, `title`, `body`, `payload` jsonb, `read_at` null, `sent_at`

The Xabarlar screen groups client-side by Today / This Week / This Month from `sent_at`.

---

## Design decisions

**1. One bookings table, two kinds.**
Restaurant and to'yxona share roughly 80% of columns — dates, status, ticket, QR, deposit, cancellation. Splitting them duplicates all of that machinery twice. One table with a `kind` discriminator plus CHECK constraints; the service layer branches per wizard.

**2. Venue type is many-to-many.**
The owner picks Restoran, To'yxona, or Barchasi. A single FK cannot express a venue that is both, and the home screen filters by type, so this must be a join table.

**3. Availability is computed, never materialized.**
Free slots derive from `venue_working_hours` + `venue_special_days` + `venue_tables` + live bookings + `venue_blocked_slots`, cached in Redis for ~14 days per venue. A pre-generated slots table would be millions of rows and still go stale on every booking.

**4. Table counts are input, tables are state.**
Onboarding asks how many 2/4/6/8/10+ seat tables exist; booking needs numbered tables. Expand at onboarding, store rows.

**5. Two QR codes, opposite directions.**
`bookings.qr_token` is shown **by** the customer **to** the venue — single use, sets `checked_in_at`. `venue_table_qrs.token` is a printed standee scanned **by** the customer to open that table's menu. Different lifecycles, different tables; do not merge.

**6. Seated duration is real data.**
`checked_in_at` on scan, `checked_out_at` when the venue closes the visit, `seated_minutes` written once. "Qoldi: 2 soat 25 daqiqa" is live arithmetic; "Umumiy o'tirildi: 4 soat" reads the stored column.

**7. Deposit is deducted, not added.**
`deposit_amount` is a percentage of `total_amount` and comes off it. `deposit_paid_at` records that it was settled; the balance is what remains against `total_amount`.

**8. Price snapshots everywhere.**
`booking_items.unit_price` + `name_snapshot`, and all `booking_price_lines`, are frozen at confirmation. Never rebuild an old receipt by joining to live `menu_items` or `venue_guest_tiers` — prices and names change.

**9. Local time for events, UTC for audit.**
`booking_date` DATE + `start_time` TIME with no conversion: 11:00 must stay 11:00. UTC applies only to `created_at`, `confirmed_at`, `checked_in_at` and similar audit columns.

**10. Translation tables, not JSONB.**
Only three languages, but user-visible text still gets `*_translations` tables (venue, venue_type, amenity, menu_category, menu_item, catering, plan). JSONB cannot be indexed or full-text searched properly. Fallback chain user language → uz → en, resolved in the service.

**11. Account deletion is a soft delete.**
"Akkauntni o'chirish" sets `status = 'deleted'` and `deleted_at`, nulls phone/email/avatar and revokes tokens. Bookings and orders stay for accounting; reviews become anonymous. A hard delete would break financial history.

**12. Denormalized counters are service-owned.**
`rating_avg` and `reviews_count` recomputed by the owning service on write. No DB triggers.

---

## Constraints and indexes

**Double booking — enforced in Postgres, not Python.**

Restaurants:
```
EXCLUDE USING gist (
    table_id WITH =,
    reserved_range WITH &&
) WHERE (status IN ('pending','confirmed','checked_in'))
```

To'yxona — a hall is booked for the whole day:
```
UNIQUE (venue_id, booking_date)
WHERE kind = 'hall_event' AND status IN ('pending','confirmed','checked_in')
```

Two users tapping "Tasdiqlash va band qilish" in the same second produce one success and one integrity error. A service-layer check alone loses that race.

**Other indexes**

| Index | Purpose |
|---|---|
| GiST on `venues.location` | `ST_DWithin` for "1 km uzoqda" |
| GIN + `pg_trgm` on `venue_translations.name` | venue search, Uzbek transliteration variants |
| GIN + `pg_trgm` on `menu_item_translations.name` | in-menu search |
| `(destination, purpose, created_at)` on verification_codes | OTP rate limiting / resend throttle |
| `(venue_id, booking_date, status)` on bookings | availability queries |

---

## Migration order

```
languages → geo → auth → catalog → venues → menu → catering
    → subscriptions → bookings → reviews → engagement
```

First revision is an empty baseline with no models. Everything depends on `languages` and `auth`, so those come first.

---

## Open questions

1. **Who pays for the subscription?** The paywall reads as a customer perk ("Foyda 20%"). If it is actually a listing fee from venue owners, `user_subscriptions` becomes `venue_subscriptions`.
2. **Restaurant deposits.** To'yxona clearly requires one. The "Depozitlik" badge appears on restaurant cards too — is it a real deposit or just a label that the venue accepts deposits?
3. **Menu pre-order payment.** The restaurant wizard shows a running total, but the ticket shows one price. Is the menu total charged up front, or is it an indication for the kitchen?
4. **Second address level naming.** "Shahar" on the owner form vs "Tuman" on the customer form. Pick one for the API.
