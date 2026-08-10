# Service plan

23 services, one class per file, no shared base, no inheritance between them.
Every constructor is `def __init__(self, session: AsyncSession) -> None` and
builds the repositories it needs.

## Conflict with the task spec, and how it is resolved

### Repositories must gain methods, so "repositories unchanged" is read as additive-only

Part B rule 5 says every read and write goes through a repository, and that a
missing query is *added to the repository, not inlined*. The prerequisite says
repositories are unchanged. Both cannot hold: ten writes the required business
rules need have no repository method today.

Resolution: **additive only.** No existing method's signature or behaviour is
touched, nothing is removed, and every addition is listed here and in
`DECISIONS.md`. The alternative — `session.add(...)` inside services — would break
rule 5 outright, and rule 5 is the one with a grep in the acceptance checklist.

Added:

| Repository | Added method | Needed by |
| --- | --- | --- |
| `BookingRepository` | `add_items`, `add_services`, `add_price_lines`, `list_items`, `list_services`, `list_price_lines`, `record_status_change` | booking price assembly, frozen lines, cancellation history |
| `VenueRepository` | `update_fields`, `add_translation`, `add_photo`, `list_photos` | onboarding wizard, venue edit |
| `UserRepository` | `update_profile` | profile edit, name promotes `pending_profile` → `active` |
| `MenuItemRepository` | `add_variant`, `list_variants`, `update_fields` | variant builder |
| `VenueServiceRepository` | `add_item`, `list_items` | dasturxon contents |
| `ReviewRepository` | `anonymise_for_user` | account deletion |
| `VenueStaffRepository` | `list_for_user` | permission guard, staff self-view |

### `uq_users_phone` does not exist; the real name is `users_phone_key`

Rule 8 requires matching `IntegrityError` on the constraint name and names
`uq_users_phone`. The column is declared `unique=True`, so Postgres generated
`users_phone_key`. Matching the spec's name would never fire. Both names are in
the map, so the code keeps working if the constraint is ever renamed.

## Transaction discipline

- A **public** method is one unit of work: reads, writes, then exactly one
  `await self.session.commit()`, and exceptions propagate.
- A method suffixed **`_in_transaction`** never commits. Cross-service reuse goes
  through those only; a public method never calls another service's public method.
- `IntegrityError` is caught at the service boundary and translated by constraint
  name in `app/core/integrity.py`, which owns the name → exception map.

## Shared infrastructure added under `app/core/`

| Module | Purpose |
| --- | --- |
| `exceptions.py` | `DomainError` base plus the 21 domain errors. Existing `AppError` subclasses stay for HTTP-shaped errors. |
| `handlers.py` | Maps `DomainError` to 404 / 403 / 409 / 422 with `{"code", "message", "details"}`. |
| `security.py` | `hash_secret` / `verify_secret` (PBKDF2-SHA256), `generate_login`, `generate_password`, `generate_token`, and the JWT encode/decode pair. |
| `integrity.py` | Constraint name → domain exception, and `translate_integrity_error`. |
| `cache.py` | `AvailabilityCache` protocol, in-memory default, Redis implementation chosen by `settings.redis.url`. |
| `transports.py` | `PushSender` protocol with a logging no-op default. The only thing mocked in tests. |

## Services

| Service | Module | Key public methods |
| --- | --- | --- |
| `AuthService` | auth | `request_code`, `verify_code`, `staff_login`, `social_login`, `refresh`, `logout` |
| `UserService` | auth | `get_profile`, `update_profile`, `delete_account` |
| `DeviceService` | auth | `register`, `list_for_user` |
| `FriendshipService` | auth | `request`, `respond`, `list_friends`, `list_incoming` |
| `LocationService` | geo | `list_regions`, `list_districts`, `list_recent`, `remember` |
| `VenueGroupService` | venue_groups | `get_for_owner`, `get_with_branches`, `update` |
| `VenueService` | venues | `search`, `get_detail`, `list_for_group`, `status_counts`, `update` |
| `VenueOnboardingService` | venues | `start`, `set_address`, `set_hours_and_seats`, `set_tables`, `set_services`, `set_media`, `finish` — each advances `onboarding_step` |
| `VenueTableService` | venues | `list_for_venue`, `create_from_counts`, `board` |
| `StaffService` | staff | `list_for_group`, `counts`, `invite`, `accept_invitation`, `set_active`, `require_permission_in_transaction` |
| `MenuService` | menu | `list_categories`, `list_items`, `get_item`, `create_item`, `set_branch_availability`, `resolve_price_in_transaction` |
| `VenueServiceCatalogService` | services | `list_catalog`, `list_for_venue`, `create`, `add_item` |
| `BookingService` | bookings | `create_table_reservation`, `create_hall_event`, `list_for_user`, `get_detail`, `cancel`, `check_in_by_qr`, `check_out`, `venue_day` |
| `AvailabilityService` | bookings | `available_tables`, `blocked_dates`, `day_slots` (Redis-cached) |
| `OrderService` | orders | `open_table`, `board`, `add_items`, `get_detail`, `close`, `cancel`, `kitchen_queue`, `add_payment` |
| `ReceiptService` | orders | `issue_in_transaction`, `get_for_order`, `reprint` |
| `SubscriptionService` | subscriptions | `list_plans`, `active_for_user`, `benefit_percent_in_transaction` |
| `ReviewService` | reviews | `create`, `list_for_venue`, `aggregate`, `publish` |
| `FavoriteService` | engagement | `toggle`, `list_for_user` |
| `ConversationService` | engagement | `open`, `list_for_user`, `send`, `history`, `mark_read` |
| `NotificationService` | engagement | `list_for_user`, `unread_count`, `mark_read`, `mark_all_read`, `notify_in_transaction` |
| `AnalyticsService` | analytics | `rollup_day`, `range_for_venue`, `compare`, `live_queue_count` |
| `DashboardService` | analytics | `owner_home` |

## Business rules, and where each lives

- **Registration state machine** — `AuthService`. No user row exists before a code
  verifies. `request_code` throttles at 3 per 10 minutes, `verify_code` locks out
  after 5 wrong attempts, codes expire at 15 minutes and are single-use.
- **Booking price assembly** — `BookingService._assemble_price_in_transaction`:
  base (tier or menu subtotal) → services → subtotal → subscription benefit →
  total → deposit as a percentage **subtracted** from the total. One frozen
  `booking_price_line` per component.
- **Booking guards** — lead time, venue open, capacity, in that order, before any
  write. Overlap is pre-checked for a readable message and the constraint remains
  the authority.
- **Check-in** — QR token, staff must have an active `venue_staff` row for that
  booking's venue, status must be `confirmed`, single use.
- **Order close** — payments must cover the total, else `PaymentIncompleteError`;
  the receipt is issued once, a second attempt is `ReceiptAlreadyIssuedError`.
- **Permissions** — `StaffService.require_permission_in_transaction`, called by
  every owner-side write. Group scope satisfies venue scope within the group.
- **Menu price** — override → base/variant → `NotFoundError`. No silent fallback.
- **Account deletion** — soft delete, contact fields nulled, tokens revoked,
  reviews anonymised; bookings and orders untouched.

## Tests

`tests/services/`, real Postgres, function-scoped transaction rolled back per
test. Only the push transport is mocked.

`test_auth_service.py`, `test_booking_service.py`, `test_order_service.py`,
`test_menu_service.py`, `test_user_service.py`.
