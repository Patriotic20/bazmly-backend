# Repository plan

45 repositories, one class per file, no shared base. Written before the files
existed; kept as the index of what they expose.

## Two things the models cannot support as specified

Both are recorded in [DECISIONS.md](DECISIONS.md). Neither model was changed —
this task is forbidden from touching them.

### 1. No `relationship()` exists on any model, so `selectinload` has no target

The models declare columns only. `inspect(Venue).relationships` is empty across
all 77. `selectinload` / `joinedload` take a relationship attribute, so hard
rule 5 cannot be executed literally.

Its *intent* — never trigger implicit IO — holds structurally instead: with no
relationships there is nothing that *can* lazy-load, so no async-IO error is
reachable. Composite reads therefore return **frozen dataclasses assembled from
explicit joins**, which is stricter than `selectinload` (one round trip, not
one-per-collection) and gives the caller a typed shape instead of an ORM object
whose loaded state depends on how it was fetched.

Affected: `VenueRepository.get_detail`, `VenueGroupRepository.get_with_branches`,
`StaffRoleRepository.get_with_permissions`, `RegionRepository.get_with_districts`,
`ReviewRepository.list_for_venue`, `BookingRepository.list_for_user`,
`VenueTableQrRepository.get_by_token`, `MenuItemRepository.get_with_variants`,
`VenueServiceRepository.get_with_items`, `ConversationRepository.list_for_user`,
`FavoriteRepository.list_for_user`.

### 2. `bookings.checked_in_by_user_id` does not exist

`check_in(booking_id, staff_id, now)` is specified to set it. Neither schema
document defines the column. The signature is kept and `staff_id` is written to
`booking_status_history.changed_by_user_id`, which exists for exactly this and
already records the `confirmed → checked_in` transition.

## Shared conventions, implemented per repository

- **Translation fallback** — a private `_translation_subquery(language_id)` per
  repository: `DISTINCT ON (parent_id)` ordered by a `CASE` priority of
  preferred → `uz` → `en` → anything. Resolved in the query; never in Python.
- **Pagination** — `Page[T]` from `app/core/pagination.py`, built directly with a
  separate `select(func.count())` over the same filters.
- **Soft delete** — `users.deleted_at IS NULL` on every read but
  `get_by_id_including_deleted`.
- **No commit** — `session.add` / `flush` / `execute` only.
- **`IntegrityError` propagates** — never caught.

## Files

### localization
`language_repository.py` — **LanguageRepository**: `list_active`, `get_by_code`,
`get_default`, `get_by_id`

### geo
`region_repository.py` — **RegionRepository**: `list_all`, `get_by_id`,
`get_with_districts` → `RegionWithDistricts`
`district_repository.py` — **DistrictRepository**: `list_by_region`, `get_by_id`
`user_recent_location_repository.py` — **UserRecentLocationRepository**:
`list_for_user`, `upsert`, `trim_to_limit`

### auth
`user_repository.py` — **UserRepository**: `get_by_id`,
`get_by_id_including_deleted`, `get_by_phone`, `get_by_email`, `get_by_login`,
`get_with_language` → `UserWithLanguage`, `exists_by_phone`, `create`,
`mark_phone_verified`, `mark_email_verified`, `touch_last_login`, `soft_delete`
`auth_identity_repository.py` — **AuthIdentityRepository**: `get_by_provider`,
`list_for_user`, `create`, `delete`
`verification_code_repository.py` — **VerificationCodeRepository**: `create`,
`get_active`, `increment_attempts`, `consume`, `count_recent`
`refresh_token_repository.py` — **RefreshTokenRepository**: `create`,
`get_by_hash`, `revoke`, `revoke_all_for_user`, `revoke_all_for_device`
`device_repository.py` — **DeviceRepository**: `get_by_uuid`, `upsert`,
`list_for_user`, `list_push_tokens_for_user`
`friendship_repository.py` — **FriendshipRepository**: `get_between`,
`list_accepted`, `list_pending_incoming`, `create`, `update_status`

### catalog
`venue_type_repository.py` — **VenueTypeRepository**: `list_active`, `get_by_id`,
`get_by_slug`
`amenity_repository.py` — **AmenityRepository**: `list_active`, `list_for_venue`,
`set_for_venue`

### venue_groups
`venue_group_repository.py` — **VenueGroupRepository**: `get_by_id`,
`get_by_owner`, `get_with_branches` → `VenueGroupWithBranches`,
`create_with_first_branch`

### venues
`venue_repository.py` — **VenueRepository**: `search` → `Page[VenueSearchRow]`,
`get_by_id`, `get_detail` → `VenueDetail`, `list_by_group`,
`count_by_status_for_group` → `VenueStatusCounts`, `is_open_at`,
`recompute_rating`, `create`, `set_status`
`venue_zone_repository.py` — **VenueZoneRepository**: `list_for_venue`,
`get_by_id`, `create`
`venue_table_repository.py` — **VenueTableRepository**: `list_for_venue`,
`get_by_id`, `bulk_create_from_counts`, `list_available`
`venue_table_qr_repository.py` — **VenueTableQrRepository**: `get_by_token` →
`TableQrContext`, `create`, `revoke`
`venue_guest_tier_repository.py` — **VenueGuestTierRepository**: `list_for_venue`,
`get_for_guest_count`, `create`
`venue_working_hours_repository.py` — **VenueWorkingHoursRepository**:
`list_for_venue`, `replace_all`

### staff
`staff_role_repository.py` — **StaffRoleRepository**: `list_active`, `get_by_id`,
`get_by_slug`, `get_with_permissions` → `StaffRoleWithPermissions`
`permission_repository.py` — **PermissionRepository**: `list_all`,
`list_slugs_for_role`, `get_by_slug`
`venue_staff_repository.py` — **VenueStaffRepository**: `list_for_group`,
`get_by_id`, `get_for_user_and_venue`, `count_by_active_for_group` →
`StaffCounts`, `has_permission`, `create`, `set_active`
`staff_invitation_repository.py` — **StaffInvitationRepository**: `create`,
`get_by_id`, `get_active_by_phone`, `accept`, `revoke`, `expire_stale`

### menu
`menu_category_repository.py` — **MenuCategoryRepository**: `list_for_group` →
`Sequence[MenuCategoryRow]` with a correlated live item count, `get_by_id`,
`create`
`menu_item_repository.py` — **MenuItemRepository**: `list_for_venue` →
`Sequence[MenuItemRow]`, `get_by_id`, `get_with_variants` → `MenuItemWithVariants`,
`resolve_price`, `set_branch_availability`, `create`

### services
`service_catalog_repository.py` — **ServiceCatalogRepository**: `list_active`,
`get_by_id`
`venue_service_repository.py` — **VenueServiceRepository**: `list_for_venue` →
`Sequence[VenueServiceRow]`, `get_with_items` → `VenueServiceWithItems`, `create`

### bookings
`booking_repository.py` — **BookingRepository**: `create_table_reservation`,
`create_hall_event`, `get_by_id`, `list_for_user` → `Sequence[UserBookingRow]`,
`list_for_venue_day`, `find_overlapping`, `get_by_qr_token`,
`get_by_receipt_number`, `check_in`, `check_out`, `expire_stale`,
`blocked_dates_for_venue`
`venue_blocked_slot_repository.py` — **VenueBlockedSlotRepository**:
`list_for_venue`, `create`, `delete`

### orders
`order_repository.py` — **OrderRepository**: `table_board` →
`Sequence[TableBoardRow]`, `open_for_table`, `get_by_id`, `get_active_for_table`,
`next_order_number`, `list_for_board`, `add_items`, `list_items`,
`recalculate_totals`, `close`, `cancel`, `kitchen_queue` →
`Sequence[KitchenQueueRow]`, `add_payment`, `list_payments`, `sum_payments`
`receipt_repository.py` — **ReceiptRepository**: `create`, `get_by_order`,
`get_by_number`, `increment_reprint`

### payments
`payment_card_repository.py` — **PaymentCardRepository**: `list_for_user`,
`get_by_id`, `get_default`, `set_default`, `get_by_token`, `create`
`payment_repository.py` — **PaymentRepository**: `create`, `get_by_id`,
`get_by_provider_transaction_id`, `list_for_booking`, `sum_paid_for_booking`,
`mark_paid`, `mark_failed`
`refund_repository.py` — **RefundRepository**: `create`, `list_for_payment`

### subscriptions
`subscription_plan_repository.py` — **SubscriptionPlanRepository**: `list_active`,
`get_by_id`
`user_subscription_repository.py` — **UserSubscriptionRepository**:
`get_active_for_user`, `get_by_id`, `list_due_for_renewal`, `mark_past_due`,
`create`

### promotions
`promo_code_repository.py` — **PromoCodeRepository**: `get_by_code`, `get_by_id`,
`increment_used`, `count_redemptions_for_user`, `record_redemption`
`user_promo_code_repository.py` — **UserPromoCodeRepository**: `list_for_user`,
`get_by_id`, `mark_used`, `expire_stale`, `create`
`banner_repository.py` — **BannerRepository**: `list_active` →
`Sequence[BannerRow]`

### reviews
`review_repository.py` — **ReviewRepository**: `list_for_venue` →
`Page[ReviewRow]`, `get_by_id`, `get_by_booking`, `aggregate_for_venue` →
`ReviewAggregate`, `list_pending`, `create`, `set_status`

### engagement
`favorite_repository.py` — **FavoriteRepository**: `exists`, `add`, `remove`,
`list_for_user` → `Sequence[FavoriteVenueRow]`
`search_history_repository.py` — **SearchHistoryRepository**: `create`,
`list_recent`
`conversation_repository.py` — **ConversationRepository**: `get_or_create`,
`get_by_id`, `list_for_user` → `Sequence[ConversationRow]`, `list_for_venue`,
`add_message`, `list_messages`, `mark_read`
`notification_repository.py` — **NotificationRepository**: `create`,
`list_for_user` → `Page[Notification]`, `count_unread`, `mark_read`,
`mark_all_read`

### analytics
`venue_daily_stats_repository.py` — **VenueDailyStatsRepository**: `upsert`,
`range_for_venue`, `sum_for_group` → `StatsTotals`,
`compare_periods` → `PeriodComparison`

## Tests

`tests/repositories/` against a real Postgres. Session-scoped engine that runs
`alembic upgrade head` once; function-scoped outer transaction rolled back after
each test, so no test sees another's writes.

Database URL from `TEST_DATABASE_URL`, else `settings.database.url` with `_test`
appended to the database name — never the dev database.

- `test_booking_repository.py` — overlapping table booking raises `IntegrityError`;
  two concurrent `create_hall_event` for one venue and date give one success and
  one `IntegrityError`; `check_in` returns `None` when status is not `confirmed`
- `test_order_repository.py` — `open_for_table` twice raises; `table_board`
  includes empty tables; `next_order_number` under two concurrent sessions never
  duplicates
- `test_venue_repository.py` — `search` orders by distance across three seeded
  venues; `is_open_now` false when a special day closes a venue inside normal hours
- `test_menu_item_repository.py` — `resolve_price` prefers the branch override and
  falls back to base price; an item with no branch row is absent from
  `list_for_venue`
