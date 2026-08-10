# Model plan

68 models across 15 modules, one model per file. All created — this file is the
plan that was written before the files, kept as the index of what exists.

## Module → model files

| Module | Models | Files |
| --- | --: | --- |
| `localization` | 1 | `language.py` |
| `geo` | 3 | `region.py`, `district.py`, `user_recent_location.py` |
| `auth` | 5 | `user.py`, `auth_identity.py`, `refresh_token.py`, `device.py`, `friendship.py` |
| `catalog` | 4 | `venue_type.py`, `venue_type_translation.py`, `amenity.py`, `amenity_translation.py` |
| `venue_groups` | 2 | `venue_group.py`, `venue_group_translation.py` |
| `venues` | 12 | `venue.py`, `venue_translation.py`, `venue_venue_type.py`, `venue_photo.py`, `venue_working_hours.py`, `venue_special_day.py`, `venue_amenity.py`, `venue_zone.py`, `venue_zone_translation.py`, `venue_table.py`, `venue_table_qr.py`, `venue_guest_tier.py` |
| `staff` | 6 | `staff_role.py`, `staff_role_translation.py`, `permission.py`, `staff_role_permission.py`, `venue_staff.py`, `staff_invitation.py` |
| `menu` | 8 | `menu_category.py`, `menu_category_translation.py`, `menu_item.py`, `menu_item_translation.py`, `menu_item_variant.py`, `menu_item_variant_translation.py`, `menu_item_branch.py`, `menu_item_variant_branch.py` |
| `services` | 4 | `service_catalog.py`, `service_catalog_translation.py`, `venue_service.py`, `venue_service_item.py` |
| `bookings` | 6 | `booking.py`, `booking_item.py`, `booking_service.py`, `booking_price_line.py`, `booking_status_history.py`, `venue_blocked_slot.py` |
| `orders` | 5 | `order.py`, `order_item.py`, `order_status_history.py`, `order_payment.py`, `receipt.py` |
| `subscriptions` | 3 | `subscription_plan.py`, `subscription_plan_translation.py`, `user_subscription.py` |
| `reviews` | 3 | `review.py`, `review_photo.py`, `review_reply.py` |
| `engagement` | 5 | `favorite.py`, `search_history.py`, `conversation.py`, `message.py`, `notification.py` |
| `analytics` | 1 | `venue_daily_stats.py` |
| **Total** | **68** | |

Not created, by instruction: `venue_hourly_load` (fixed decision 8) and the four
`catering_*` tables (fixed decision 6, superseded by `service_catalog` /
`venue_services` / `venue_service_items`).

Each module also has the standard skeleton — `api/` with `v1/`, `v2/` and
`router.py`; `repositories/`; `services/`; `schemas/` — all empty per hard rule 7.

## Tables without `TimestampMixin`

Three pure association tables. The schema docs give them no `id`, so they take a
composite primary key and no audit columns:

`venue_venue_types`, `venue_amenities`, `staff_role_permissions`.

`menu_item_branches`, `menu_item_variant_branches` and `favorites` are *not* in
that set: the docs give them payload columns and a separate `UNIQUE`, so they
keep `IdIntPk` and `TimestampMixin`.

## Migration order

17 revisions, one per module plus extensions and seed:

```
extensions → localization → geo → auth → catalog → venue_groups → venues
  → staff → menu → services → subscriptions → bookings → orders
  → reviews → engagement → analytics → seed
```

### Forward-pointing foreign key

One FK points at a table that the fixed order creates later, so it is created by
a subsequent revision instead of with its own table:

| Column | Target | Created in |
| --- | --- | --- |
| `user_recent_locations.user_id` | `users` | `auth` |

It is a genuine cycle: `geo.user_recent_locations` → `users`, while
`auth.users` → `districts`.

## Source coverage

Both authoritative documents are in [docs/](docs/):

- [`bazmly-db-schema.md`](docs/bazmly-db-schema.md) — Part 1, customer app, sections 1–13
- [`db-schema-part2-venue-app.md`](docs/db-schema-part2-venue-app.md) — Part 2, venue app, deltas plus sections 14–19

Where Part 2 lists a delta to a Part 1 table, the model reflects the merged final
state — `venues` carries `venue_group_id`, `manager_user_id`, `onboarding_step`
and `status = 'closed'` from the start; `venue_tables` has `zone_id` and never the
dropped `zone` enum; `menu_categories` hangs off `venue_group_id`, not `venue_id`.
