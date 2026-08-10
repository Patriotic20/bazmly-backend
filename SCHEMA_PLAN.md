# Schema plan

Pydantic v2. One file per entity holding that entity's whole family, under
`app/modules/<module>/schemas/`.

## Conflicts with the task spec, and how they are resolved

### Enums cannot move into `enums.py` without editing models

The spec wants enums declared once in `app/modules/<module>/enums.py`, with models
importing them. All 25 are currently declared inside model files, and this task may
not modify models.

`enums.py` therefore **re-exports** the model-declared enums. There is still
exactly one declaration of each, models and schemas share the same objects, and no
schema redeclares one — which is what the rule protects. When models may be
touched again, moving the `class X(StrEnum)` bodies into `enums.py` and importing
them back into the models is a mechanical change that breaks nothing.

### Money uses an annotated serializer, not a per-field `field_serializer`

The spec says to serialise money with `field_serializer`. There are ~60 money
fields across ~25 schemas; a decorator per field is repetition that fails open —
forget one and that field silently ships as a JSON number.

`app/core/schemas.py` defines instead:

```python
Money = Annotated[Decimal, PlainSerializer(_money_to_str, return_type=str)]
```

Same mechanism, attached to the type rather than restated at each use, so a field
typed `Money` cannot be serialised any other way. Every money field is `Money` and
travels with its `currency`.

## Shared pieces — `app/core/schemas.py`

| Name | Purpose |
| --- | --- |
| `ReadSchema` | Base with `ConfigDict(from_attributes=True)`. Rule 1 satisfied by inheritance. |
| `UpdateSchema` | Base with a `model_validator` that raises when `model_fields_set` is empty, so a no-op PATCH is 422 rather than a silent 200. |
| `Money` | `Decimal` serialised to a 2-dp string. |
| `PhoneNumber` | `str` normalised to E.164 and rejected unless `+998` + 9 digits. |

Pagination reuses `Page[T]` from `app/core/pagination.py`.

## Rules applied uniformly

- **Secrets never appear in a read schema.** `password_hash`, `code_hash`,
  `token_hash`, `temp_password_hash`, `provider_token`, `raw_profile` are absent
  from every `*Read` / `*ListItem`. `qr_token` appears only on
  `BookingOwnerDetail`, the booking owner's own response — never in a list, never
  in a venue-side schema.
- **Translations are flattened.** `name` / `description` are plain resolved
  strings. No schema exposes a translation row.
- **Computed presentation values are declared fields**, filled by the service:
  `distance_m`, `is_open_now`, `elapsed_seconds`, `effective_price`.
- **Local vs UTC.** `booking_date: date`, `start_time` / `end_time`: `time`, never
  combined. Audit stamps are naive UTC `datetime`.

## Families

42 families. `C` = Create, `U` = Update, `R` = Read, `L` = ListItem,
`S` = SearchParams.

| Module | File | Variants |
| --- | --- | --- |
| localization | `language.py` | R |
| geo | `region.py` | R |
| geo | `district.py` | R |
| geo | `user_address.py` | C R (recent locations) |
| auth | `user.py` | C U R L + `UserProfileUpdate` |
| auth | `auth.py` | `PhoneCheck`, `PhoneCheckResult`, `PhoneRegister`, `PhoneLogin`, `GoogleLogin`, `PasswordChange`, `StaffLogin`, `TokenPair`, `RefreshRequest` |
| auth | `device.py` | C R |
| auth | `friendship.py` | C R + `FriendshipRequestAction` |
| catalog | `venue_type.py` | R |
| catalog | `amenity.py` | R |
| venue_groups | `venue_group.py` | C U R + `VenueGroupWithBranchesRead` |
| venues | `venue.py` | C U R L S + `VenueDetailRead` |
| venues | `venue_zone.py` | C R |
| venues | `venue_table.py` | C R + `TableCountsCreate` |
| venues | `venue_guest_tier.py` | C R |
| venues | `working_hours.py` | C R + `WorkingHoursReplace` |
| staff | `staff_role.py` | R |
| staff | `permission.py` | R |
| staff | `venue_staff.py` | C U R L + `StaffCountsRead` |
| staff | `staff_invitation.py` | C R + `InvitationAccept` |
| menu | `menu_category.py` | C U R |
| menu | `menu_item.py` | C U R L + `BranchAvailabilityUpdate` |
| menu | `menu_item_variant.py` | C U R |
| services | `service_catalog.py` | R |
| services | `venue_service.py` | C U R + `VenueServiceItemCreate/Read` |
| bookings | `booking.py` | `TableReservationCreate`, `HallEventCreate`, U R L, `BookingOwnerDetail`, S |
| bookings | `booking_item.py` | C R |
| bookings | `booking_service.py` | C R |
| bookings | `price_line.py` | R |
| orders | `order.py` | C U R L + `TableBoardRow`, `OrderDetailRead` |
| orders | `order_item.py` | C U R + `KitchenQueueItem` |
| orders | `order_payment.py` | C R |
| orders | `receipt.py` | C R |
| subscriptions | `subscription_plan.py` | R |
| subscriptions | `user_subscription.py` | C R |
| reviews | `review.py` | C U R L + `ReviewAggregateRead` |
| engagement | `favorite.py` | C R |
| engagement | `conversation.py` | C R L |
| engagement | `message.py` | C R |
| engagement | `notification.py` | R + `UnreadCount` |
| analytics | `venue_daily_stats.py` | R + `PeriodComparisonRead` |
| analytics | `dashboard.py` | `DashboardRead` — the owner-home aggregate |

`booking_item`, `booking_service`, `price_line`, `order_item`, `order_payment` and
`receipt` live in their parent's module but their own file, because each is a
distinct entity family even though it is written through its parent's repository.
