# Bazmly — Database Schema, Part 2: Venue App

Companion to `bazmly-db-schema.md`. Derived from the venue-owner / staff app screens: owner onboarding, dashboard, Filiallar, Hodimlar, Buyurtmalar, the menu builder, and Sozlamalar.

Everything in Part 1 still holds. This document does two things:

1. **Deltas** — columns, enums and tables that change on structures that already exist.
2. **New sections 14–19** — chains, staff, orders, services, analytics.

Section numbering continues from Part 1 so the two files can be concatenated into one reference.

**Stack:** unchanged — PostgreSQL, SQLAlchemy 2.0 async, Alembic
**Conventions:** unchanged — integer PKs, naive UTC audit timestamps, `Numeric(14,2)` + currency column

---

## Table of contents

1. [Deltas to Part 1 tables](#deltas-to-part-1-tables)
2. [14. chains](#14-chains)
3. [15. staff](#15-staff)
4. [16. orders](#16-orders)
5. [17. menu (revised)](#17-menu-revised)
6. [18. services](#18-services)
7. [19. analytics](#19-analytics)
8. [Design decisions (13–25)](#design-decisions-1325)
9. [Constraints and indexes (additions)](#constraints-and-indexes-additions)
10. [Migration plan](#migration-plan)
11. [Screen → table map](#screen--table-map)
12. [Open questions (5–14)](#open-questions-514)

---

## Deltas to Part 1 tables

### users

| Change | Column | Notes |
|---|---|---|
| add | `theme` enum(system, light, dark) default system | the "Mode" toggle on Sozlamalar |

No change to `role`. A cook is a `users` row with `role = 'venue_staff'`; which cook, at which branch, with what rights, lives in `venue_staff` (§15).

### venues — a venue is now a **branch**

| Change | Column | Notes |
|---|---|---|
| add | `venue_group_id` FK venue_groups NOT NULL | see §14 |
| add | `manager_user_id` FK users null | "Menejer tanlash" on the add-branch form |
| add | `onboarding_step` smallint default 0 | 0–5, resume a half-finished wizard |
| extend | `status` enum | append `closed` |

**`status = 'closed'` is not the same as being shut for the night.** The Filiallar counters read Jami 3 / Aktiv 2 / Yopiq 1, and the Yunusobod card shows the Yopiq badge at 9:41 while its hours are 08:00–20:00 — inside the window. So that badge is persistent state, not a clock. The green "Ochiq" pill on the dashboard header *is* the clock, computed from `venue_working_hours` at render time. Same word, two meanings; keep them apart in the API (`status` vs `is_open_now`).

### venue_translations

| Change | Column | Notes |
|---|---|---|
| add | `tagline` varchar(120) null | branch card subtitle: "Premium Filial", "Family Restaurant", "Kafe" |

### venue_tables

| Change | Column | Notes |
|---|---|---|
| drop | `zone` enum(indoor, terrace, vip) | replaced |
| add | `zone_id` FK venue_zones null | |

### venue_zones (new)

`id`, `venue_id` FK, `slug`, `sort_order`, `is_active`
`venue_zone_translations`: `id`, `zone_id` FK, `language_id` FK, `name` — `UNIQUE (zone_id, language_id)`

Seed per branch: `ichkari`, `tashqari`. **"Umumiy" is a UI shortcut meaning no zone filter, not a zone row** — the same pattern as "Barchasi" in the venue-type picker (Part 1, decision 2). A terrace-only kafe and a three-floor restaurant cannot share a fixed enum, so zones are rows.

### venue_staff

Rewritten. See §15.

### menu_categories, menu_items

Ownership moves from the branch to the chain, and items gain variants. See §17.

---

## 14. chains

### venue_groups

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| owner_id | FK users | the account created at registration |
| primary_venue_type_id | FK venue_types | restoran / to'yxona, picked on the signup screen |
| logo_url | text null | 500×500 |
| default_currency | char(3) | UZS |
| status | enum | draft, active, blocked |

### venue_group_translations

`id`, `venue_group_id` FK, `language_id` FK, `name`, `description` — `UNIQUE (venue_group_id, language_id)`

"Tinchlik Plaza" in the dashboard header is the group name. Branch names ("Tashkent City", "Chilonzor", "Yunusobod") stay in `venue_translations`.

**Every venue belongs to a group, including a single restaurant that will never open a second location.** Onboarding creates the group and its first branch in one transaction. The alternative — nullable `venue_group_id`, branch logic only when set — means every menu query, every permission check and every dashboard aggregate needs two code paths forever. A group of one costs one row.

---

## 15. staff

Staff authenticate as normal `users`, so `refresh_tokens`, `devices` and `verification_codes` from Part 1 are reused unchanged. This section covers only employment: who works where, as what, with which rights.

### staff_roles

`id`, `slug` unique, `scope` enum(group, venue), `is_system` bool, `sort_order`, `is_active`

Seed from the Lavozim picker: `owner` (group), `admin` (group), `manager` (venue), `waiter`, `cook`, `cook_assistant`, `security`.

### staff_role_translations

`id`, `staff_role_id` FK, `language_id` FK, `name` — `UNIQUE (staff_role_id, language_id)`

Uzbek seed: Egasi, Admin, Menendjer, Ofitsant, Oshpaz, Oshpaz yordamchisi, Qo'riqchi. The role badge colours on the Hodimlar cards are a client concern; do not store them.

### permissions

`id`, `slug` unique, `group` varchar

Seed: `branch.manage`, `branch.create`, `staff.manage`, `menu.edit`, `menu.publish`, `orders.open`, `orders.add_items`, `orders.close`, `orders.discount`, `bookings.confirm`, `bookings.cancel`, `reports.view`, `settings.edit`.

### staff_role_permissions

`staff_role_id` FK, `permission_id` FK — PK on both

"Menejer filialni to'liq boshqarish huquqiga ega bo'ladi" is a sentence under a form field today. Written as rows it is checkable at the API layer and editable later without a deploy.

### venue_staff (rewritten)

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| venue_group_id | FK venue_groups | always set |
| venue_id | FK venues null | null = group-level (owner, admin) |
| user_id | FK users | |
| staff_role_id | FK staff_roles | |
| login | varchar(32) unique | auto-generated, sent by SMS |
| password_hash | varchar | |
| must_change_password | bool | true until first successful login |
| is_active | bool | the "Active Status" toggle |
| invited_by_user_id | FK users null | |
| invited_at | timestamp | |
| activated_at | timestamp null | first login |
| deactivated_at | timestamp null | |

`UNIQUE (venue_id, user_id)`. `CHECK`: `staff_roles.scope = 'venue'` → `venue_id IS NOT NULL`.

Jami / Aktiv / Noaktiv on the Hodimlar header are `COUNT(*)`, `COUNT(*) FILTER (WHERE is_active)`, and the remainder — cheap enough to compute live at 45 rows, and it must be exact.

### staff_invitations

`id`, `venue_group_id` FK, `venue_id` FK null, `full_name`, `phone` varchar(20), `staff_role_id` FK, `temp_password_hash`, `sms_sent_at` null, `sms_provider_id` null, `accepted_at` null, `expires_at`, `revoked_at` null

The add-employee form promises "Login va vaqtinchalik parol avtomatik tarzda SMS orqali yuboriladi". **Store the hash, never the password** — same rule as `verification_codes`. The temporary password expires (72h is a reasonable default) and `must_change_password` forces rotation on first login, so a forwarded SMS is not a permanent key to the till.

---

## 16. orders

The Buyurtmalar tab. **An order is not a booking.** A booking is a promise made in the customer app before arrival; an order is an open check on a table right now, and most of them belong to walk-ins who never booked. They share almost nothing: no ticket, no QR, no deposit, no cancellation window, different lifecycle, different writers. `orders.booking_id` links the two when a booked guest sits down.

### orders

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| venue_id | FK venues | branch |
| table_id | FK venue_tables null | null for takeaway |
| booking_id | FK bookings null | set when the guest arrived on a reservation |
| order_number | int | per branch, per day |
| kind | enum | dine_in, takeaway |
| status | enum | open, in_progress, served, awaiting_payment, completed, cancelled |
| guests_count | smallint null | |
| waiter_staff_id | FK venue_staff null | "Ofitsiant: Jasur A." |
| opened_by_staff_id | FK venue_staff | |
| closed_by_staff_id | FK venue_staff null | |
| subtotal | numeric(14,2) | |
| discount_amount | numeric(14,2) | |
| service_charge | numeric(14,2) | |
| total_amount | numeric(14,2) | "Jami summa" |
| currency | char(3) | |
| opened_at | timestamp | |
| closed_at | timestamp null | |
| cancelled_at | timestamp null | |
| cancel_reason | text null | |

`UNIQUE (venue_id, business_date, order_number)`.

The elapsed timers on the cards — `12:30`, `05:45`, `25 min` — are `now() - opened_at`, computed at render. Never stored, never polled from the server as a number.

### order_items

`id`, `order_id` FK, `menu_item_id` FK, `variant_id` FK menu_item_variants null, `quantity`, `unit_price`, `discount_amount`, `total_price`, `name_snapshot`, `variant_name_snapshot` null, `status` enum(new, sent_to_kitchen, cooking, ready, served, cancelled), `note` text null, `added_by_staff_id` FK, `added_at`, `served_at` null

Item-level status exists because Oshpaz is a role in this app. The kitchen queue is `order_items WHERE status IN ('sent_to_kitchen','cooking')`, which is a per-dish question, not a per-check one. "Qo'shish +" on an open check appends rows; "+ yana 2 ta mahsulot" is a client-side truncation of the same list.

Prices are snapshotted at insert, per Part 1 decision 8.

### order_status_history

`id`, `order_id` FK, `from_status`, `to_status`, `changed_by_staff_id` FK null, `comment`, `changed_at`

### order_payments

`id`, `order_id` FK, `method` enum(cash, card, transfer, click, payme, other), `amount`, `currency`, `received_by_staff_id` FK, `paid_at`, `provider_transaction_id` null, `change_amount` null

Split payments are one order, several rows. `SUM(amount) >= total_amount` is a service-layer check before the close, not a constraint — partial payment on an open check is legal.

### receipts

`id`, `order_id` FK unique, `receipt_number` varchar unique, `printed_at`, `printed_by_staff_id` FK, `fiscal_sign` varchar null, `fiscal_serial` varchar null, `payload` jsonb, `reprinted_count` smallint

"Ushbu harakat stolni yopadi va chekni chop etadi." A receipt row is written once and never updated; a correction is a new order or a refund, not an edit. `payload` freezes the printed lines so a reprint two months later is byte-identical regardless of what happened to the menu.

### Table board

There is no `venue_tables.state` column and no `table_sessions` table. The board is a left join:

```sql
SELECT t.*, o.id AS order_id, o.status, o.opened_at
FROM venue_tables t
LEFT JOIN orders o
  ON o.table_id = t.id
 AND o.status NOT IN ('completed','cancelled')
WHERE t.venue_id = :venue_id AND t.is_active
```

`order_id IS NULL` → Bo'sh. Otherwise the chip follows `orders.status`. One open order per table is enforced in Postgres (see indexes below), so the join can never fan out and two waiters cannot open the same table twice.

---

## 17. menu (revised)

Part 1 hung `menu_categories` off `venue_id`. Step 3 of the menu builder — "Filiallarni tanlash: Qaysi filiallarda bu taom mavjud bo'ladi?" with a per-branch "Maxsus narx" override — says otherwise. **The dish belongs to the chain; availability and price belong to the branch.**

### menu_categories

| Change | Column | Notes |
|---|---|---|
| replace | `venue_id` → `venue_group_id` FK venue_groups | |

The chips (Go'shlik taomlar, Steyklar, Ichimliklar) carry a count — `5` on Steyklar — which is a live `COUNT(*)` over available items, not a stored column.

### menu_items

| Change | Column | Notes |
|---|---|---|
| replace | `price` → `base_price` numeric null | null when `has_variants` |
| add | `has_variants` bool default false | the "Variant mavjudmi?" toggle |
| add | `discount_percent` numeric(5,2) null | "Chegirma", optional |
| add | `status` enum(active, hidden, out_of_stock) | the Status toggle on step 1 |
| keep | `photo_url` | JPG/PNG, ≤5 MB, validated in the service |

`CHECK (has_variants = false AND base_price IS NOT NULL) OR (has_variants = true AND base_price IS NULL)`.

### menu_item_variants

`id`, `menu_item_id` FK, `price` numeric, `sort_order`, `is_active`

### menu_item_variant_translations

`id`, `variant_id` FK, `language_id` FK, `name` — `UNIQUE (variant_id, language_id)`

Kichik / O'rtacha / Katta are user-visible strings, so they get a translation table like everything else (Part 1, decision 10). Portion sizes are not an enum: a pizzeria's variants are not a teahouse's.

### menu_item_branches

`menu_item_id` FK, `venue_id` FK, `is_available` bool, `price_override` numeric null, `variant_price_overrides` jsonb null

`UNIQUE (menu_item_id, venue_id)`.

Resolution order for a price: `price_override` → `menu_items.base_price` (or the variant's price) → error. A row exists only for branches the owner ticked; an unticked branch has no row and does not show the dish. `variant_price_overrides` is the one deliberate JSONB in the schema — it is a `{variant_id: price}` map that is never searched, never sorted and never joined, only read whole alongside its parent row.

---

## 18. services

The "Qo'shimcha xizmatlar" step of owner onboarding: a fixed picker (Dasturxon tuzash, Raqqoslar, Kartej, Video, Qo'shiqchi, Sahna), each with a price, and Dasturxon tuzash additionally holding a list of dishes with their own prices.

### service_catalog

`id`, `slug` unique, `icon_url`, `applies_to_venue_type_id` FK null, `sort_order`, `is_active`

### service_catalog_translations

`id`, `service_catalog_id` FK, `language_id` FK, `name` — `UNIQUE (service_catalog_id, language_id)`

A closed platform-owned list, because the onboarding screen offers a closed list. If owners are later allowed free-text services, add `venue_services.custom_name` rather than letting them write into the catalog.

### venue_services

`id`, `venue_group_id` FK, `venue_id` FK null, `service_catalog_id` FK, `price` numeric, `currency`, `price_unit` enum(flat, per_guest, per_hour), `is_active`, `sort_order`

`venue_id IS NULL` means the price applies across the whole chain. "7 mln so'm" for Raqqoslar is `price` with `price_unit = 'flat'`.

### venue_service_items

`id`, `venue_service_id` FK, `name`, `price` numeric, `sort_order`

The Taomlar rows nested under Dasturxon tuzash. Not `menu_items` — these are the fixed contents of a wedding table sold as one package, not à-la-carte dishes with photos, variants and per-branch availability.

### booking_services

`id`, `booking_id` FK, `venue_service_id` FK, `quantity`, `unit_price`, `name_snapshot`, `total_price`

Feeds `booking_price_lines` with `line_type = 'service_logistics'` at confirmation.

> **Overlap warning.** Part 1's `catering_packages` / `catering_sections` model the customer-facing dasturxon with its Salatlar / Mevalar / Asosiy taomlar sections. `venue_services` + `venue_service_items` is the owner-side input for what looks like the same thing. Two writable sources for one price will drift. See open question 8.

---

## 19. analytics

The dashboard asks for a weekday bar chart, a month total, and a percentage delta on every card. Running those over raw `bookings` and `orders` on each app open is a full scan per owner per refresh.

### venue_daily_stats

`id`, `venue_id` FK, `business_date` date, `bookings_count`, `guests_count`, `no_show_count`, `cancelled_count`, `orders_count`, `revenue` numeric, `avg_check` numeric, `occupancy_percent` numeric(5,2), `computed_at`

`UNIQUE (venue_id, business_date)`.

Written by a nightly job for closed days and refreshed incrementally for today on order close. The chain-level numbers on the dashboard are a `SUM` across the group's branches.

**Deltas are computed at read, not stored.** "+12%" is this period against the previous one; storing it means storing it wrong the moment a late cancellation lands. "Hozirgi navbat — 20 ta" is live: today's `confirmed` bookings that have not checked in.

### venue_hourly_load

`id`, `venue_id` FK, `business_date`, `hour` smallint, `bookings_count`, `covers_count`

Not on any screen yet. Cheap to write next to the daily rollup, and the first thing anyone asks for after the weekday chart ships.

---

## Design decisions (13–25)

**13. Branches are venues; the chain is a group.**
A branch has an address, a phone, its own tables, its own hours, its own bookings — that is `venues`, unchanged. What the owner app adds above it is a brand, and brands own menus and staff. Self-referencing `parent_venue_id` would have made "is this row a brand or a place?" a runtime question on every query.

**14. Every venue has a group, even alone.**
No nullable branching. Onboarding writes the group and the first branch together.

**15. The menu belongs to the chain, availability to the branch.**
Step 3 of the builder is the whole argument: one dish, ticked into some branches, with a different price in one of them.

**16. Orders are not bookings.**
Different lifecycle, different actors, different columns. `orders.booking_id` joins them when the same guest is both.

**17. Table state is derived, and the race is settled in Postgres.**
No state column that can disagree with the orders table. A partial unique index on `table_id` for live orders means two waiters tapping the same empty table produce one check and one integrity error — the same reasoning as the double-booking exclusion constraint in Part 1.

**18. Item-level status, because the kitchen is a separate role.**
Oshpaz needs a dish queue, not a check queue.

**19. Staff credentials are hashes with an expiry.**
Auto-generated login, temporary password over SMS, hash only, forced rotation on first login. An SMS is forwardable; a permanent password in it is a permanent hole in the till.

**20. Roles are rows and permissions are rows.**
Six roles today, and the manager's authority is currently a sentence in a form hint. Rows make it enforceable and let the seventh role ship without a migration.

**21. Zones are rows; "Umumiy" is a shortcut.**
Same pattern as "Barchasi" in the venue-type picker: a filter that means *no filter*, not a value.

**22. Variants replace the base price, they do not sit beside it.**
A CHECK constraint, not a convention. Otherwise every price read has to guess which of two columns is authoritative.

**23. The receipt is immutable.**
Written once with a frozen payload. Corrections are new rows. Reprints increment a counter and change nothing else.

**24. The dashboard reads rollups.**
Raw aggregation per app open does not survive a chain with real volume. Rollup nightly, refresh today's row on close, compute percentages at read.

**25. "Ochiq" and "Aktiv" are different questions.**
`venues.status` is administrative and persistent. Open-right-now is `venue_working_hours` plus the clock. The Filiallar screen shows both in the same pill, which is fine for a card and fatal for an API field name.

---

## Constraints and indexes (additions)

**One open check per table — enforced in Postgres.**

```sql
CREATE UNIQUE INDEX one_open_order_per_table
    ON orders (table_id)
 WHERE table_id IS NOT NULL
   AND status NOT IN ('completed', 'cancelled');
```

**Other indexes**

| Index | Purpose |
|---|---|
| `(venue_id, status, opened_at)` on orders | the Buyurtmalar board and its status chips |
| `(venue_id, business_date)` on orders | daily order numbering, day close |
| `(order_id, status)` on order_items | kitchen queue |
| `(venue_group_id, is_active)` on venue_staff | Jami / Aktiv / Noaktiv counters |
| `(venue_id, staff_role_id)` on venue_staff | the role filter chips |
| `UNIQUE (menu_item_id, venue_id)` on menu_item_branches | one price rule per branch per dish |
| `(venue_group_id, sort_order)` on menu_categories | menu load |
| `UNIQUE (venue_id, business_date)` on venue_daily_stats | idempotent rollup |
| `(venue_group_id, status)` on venues | Filiallar counters |
| `(phone, expires_at)` on staff_invitations | invite throttling |

---

## Migration plan

Each numbered item is one Alembic revision. Nothing here drops data.

1. **`venue_groups`, `venue_group_translations`** — create.
2. **`venues.venue_group_id`** — add nullable, backfill one group per distinct `owner_id`, copy `venue_translations.name` into the group, set NOT NULL.
3. **`venues`** — add `manager_user_id`, `onboarding_step`; append `closed` to the status enum; add `venue_translations.tagline`.
4. **`venue_zones`, `venue_zone_translations`** — create, seed ichkari/tashqari per venue, add `venue_tables.zone_id`, map the old enum (`indoor`→ichkari, `terrace`→tashqari, `vip`→a new row), drop `venue_tables.zone`.
5. **`staff_roles`, `staff_role_translations`, `permissions`, `staff_role_permissions`** — create and seed.
6. **`venue_staff`** — add the new columns, map the old `role` enum onto `staff_role_id` (`owner`→owner, `manager`→manager, `waiter`→waiter), drop `role`. Create `staff_invitations`.
7. **menu move** — add `menu_categories.venue_group_id`, backfill from `venues.venue_group_id`, set NOT NULL, drop `venue_id`. Add the new `menu_items` columns, rename `price`→`base_price`. Create `menu_item_variants`, `menu_item_variant_translations`, `menu_item_branches`, then backfill one `menu_item_branches` row per existing item × its original venue so nothing disappears from a live menu.
8. **`service_catalog`, `service_catalog_translations`, `venue_services`, `venue_service_items`, `booking_services`** — create and seed the catalog.
9. **`orders`, `order_items`, `order_status_history`, `order_payments`, `receipts`** — create, including the partial unique index.
10. **`venue_daily_stats`, `venue_hourly_load`** — create, then backfill from history in a data-only revision.
11. **`users.theme`** — add.

Steps 2, 4, 6 and 7 each contain a backfill. Split each into schema-then-data revisions if the production table is large enough that a single transaction would hold locks too long.

---

## Screen → table map

| Screen | Tables |
|---|---|
| Tizim tilini tanlang | `languages` |
| Akkaunt yaratish, SMS code | `users`, `verification_codes`, `refresh_tokens` |
| Restoraningizni kiriting | `venue_groups`, `venues`, `venue_translations`, `venue_venue_types` |
| Manzil (viloyat / shahar / ko'cha / xarita) | `regions`, `districts`, `venues` |
| Vaqt & Zal sozlamalari | `venues.total_seats`, `venue_working_hours`, `venues.min_advance_booking_days` |
| Stollar (2/4/6/8/10+ counts) | `venue_tables` — expanded from counts, Part 1 decision 4 |
| Qo'shimcha xizmatlar | `service_catalog`, `venue_services`, `venue_service_items` |
| Media va vizual | `venue_groups.logo_url`, `venue_photos` |
| Restaurant is live | `venues.status`, `venues.onboarded_at` |
| Dashboard | `venue_daily_stats`, live `bookings`, `venues`, `venue_staff` |
| Kutilayotgan mijozlar | `bookings`, `booking_status_history` |
| Filiallar | `venues`, `venue_translations`, `venue_working_hours`, `venue_daily_stats` |
| Yangi filial qo'shish | `venues`, `venues.manager_user_id`, `venue_working_hours` |
| Hodimlar | `venue_staff`, `staff_roles`, `users` |
| Xodim qo'shish | `staff_invitations`, `venue_staff`, `users` |
| Buyurtmalar — Stollar board | `venue_tables`, `venue_zones`, `orders` |
| Buyurtmalar — order card | `orders`, `order_items`, `venue_staff` |
| Yakunlash modal | `orders`, `order_payments`, `receipts` |
| Menyu grid + stepper | `menu_categories`, `menu_items`, `menu_item_branches`, `order_items` |
| Menyu builder steps 1–4 | `menu_items`, `menu_item_variants`, `menu_item_branches` |
| Sozlamalar | `users`, `venues`, `venue_working_hours` |
| Til sozlamalari | `languages`, `users.language_id` |
| Xabarlar | `notifications` |

---

## Open questions (5–14)

Continuing the numbering from Part 1.

5. **Can one person work at two branches?** `venue_staff` allows it — two rows, two roles. The Hodimlar screen shows a flat list with no branch column, so either it is scoped to the current branch and the UI is missing a label, or staff are chain-wide and the model is over-built.

6. **Which branch is the dashboard showing?** The header reads "Tinchlik Plaza" (the group) but the working hours and the Ochiq badge below it belong to a single branch. Chain totals with one branch's hours is a mixed view. Needs a branch switcher or a defined default.

7. **"Restoranlar soni — 2 ta" counts active branches, not all of them.** Filiallar says Jami 3, Aktiv 2, Yopiq 1. If that is deliberate, label it Aktiv filiallar; if not, the dashboard query is missing the closed one.

8. **`venue_services` vs `catering_packages`.** Same dasturxon, two tables, two write paths. Recommendation: keep `venue_services` + `venue_service_items` as the single writable source and derive the customer-facing package view from it, deleting `catering_sections` — but this touches shipped customer screens, so it is a call for the team.

9. **Does closing a check require a payment row?** The modal only mentions closing the table and printing. If cash is settled off-app, `order_payments` will be sparse and `revenue` in the rollups becomes fiction.

10. **Fiscal receipts.** `fiscal_sign` and `fiscal_serial` are reserved on `receipts`, but nothing in the screens says whether the app is the fiscal register or prints an informational slip. This changes what "print" means legally and cannot be retrofitted quietly.

11. **Tashqari — terrace or takeaway?** It sits on a *table* board next to Ichkari, which reads as outdoor seating. But a takeaway order has no table, and `orders.kind` currently assumes takeaway exists. Confirm which.

12. **Is the Menyu tab an ordering screen?** It has a quantity stepper and a "Keyingis" button, which is a waiter taking an order, not an owner editing a catalogue. If both, the same screen needs two permission sets.

13. **"Add friends" on the owner profile.** `friendships` was built for the customer app. On a business account it is either a staff-invite button wearing the wrong label, or a screen copied across unchanged.

14. **Which venue do Sozlamalar's hours and table counts edit?** For a chain, editing hours from the profile screen has to target a branch. Right now it targets whatever the app considers current.
