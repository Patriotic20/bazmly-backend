# API plan

Routers, endpoints, dependencies and OpenAPI metadata. Version before module:
`/api/v1/<module>/...`, staff-facing trees under `/api/v1/venue/...`.

## Wiring

```python
# app/modules/<module>/api/v1/router.py     -> APIRouter(prefix="/v1/<module>", tags=["<module>"])
# app/modules/<module>/api/router.py        -> APIRouter() including v1 + v2
# app/core/router.py                        -> APIRouter(prefix="/api") including every module router
```

`v2/router.py` exists in all 15 modules with no endpoints — a placeholder, never a
mirror of v1.

Where a module serves both audiences, `v1/` splits into `customer.py` and
`venue.py` and `v1/router.py` includes both. Roles are never branched on inside an
endpoint: a staff booking list and a guest booking list are different payloads with
different filters, so they are different endpoints.

## Auth

**PyJWT**, chosen over python-jose: it is the smaller dependency, actively
maintained, and everything needed here is HS256 encode/decode.

- Access token — 15 min, claims `sub` (user id), `jti`, `type: "access"`, `exp`,
  `iat`. Stateless, no DB row.
- Refresh token — 30 days, stored hashed in `refresh_tokens`, rotated on every use.
  Presenting an already-revoked token revokes **every** token for that user, on the
  theory that a revoked token in the wild means the family is compromised.
- Staff and customers carry the same token type. Authority comes from `venue_staff`
  + permissions at request time, never from a claim — so a role change takes effect
  immediately instead of waiting out a token's expiry.

Access tokens are minted **at the API boundary**, not by `AuthService`. The service
owns the refresh-token lifecycle (rows, rotation, revocation); a stateless bearer
credential with no row is a transport concern. See DECISIONS.md.

## Dependencies — `app/core/dependencies.py`

| Name | Purpose |
| --- | --- |
| `get_session` | Wraps `db_helper.session_getter`. The only place a session enters a request. |
| `get_current_user` | Decodes the access token, loads the user, rejects non-`active` and soft-deleted. Raises `AuthenticationRequiredError` (401) for a missing or unreadable token and `PermissionDeniedError` (403) for a blocked account, never `HTTPException`. |
| `get_current_user_optional` | For endpoints that personalise but do not require auth (venue search, venue detail). |
| `require_permission(slug)` | `Depends(PermissionRequired(slug))`. Resolves the user, reads `venue_id` from path or query, calls `StaffService.require_permission_in_transaction`, and **returns the user**. Group scope satisfies venue scope. In a signature it replaces `user: CurrentUser`; in `dependencies=[...]` it only guards. |
| `require_group_permission(slug)` | `Depends(GroupPermissionRequired(slug))`. The same, resolving `group_id` — for routes that create a branch, which have no `venue_id` yet. |
| `get_language_id` | `Accept-Language` → authenticated user's `language_id` → `uz`. |
| `get_pagination` | `limit` (20, max 100) and `offset`, as a frozen dataclass. |
| `get_client_location` | Optional `lat`/`lng`, validated as a pair — both or neither. |

Per-module `api/dependencies.py` holds thin service factories only.

## Error envelope

One handler per `DomainError` subclass in `app/core/handlers.py`, mapping to
401 / 403 / 404 / 409 / 422 / 429. Body is always
`{"code", "message", "details", "request_id"}`.

401 and 403 divide on whether signing in again would help: no token or an
unreadable one is a 401, a caller we identified and still refuse — blocked
account, missing permission — is a 403.

## Routes

`A` = access token, `R` = refresh token, `P:slug` = `require_permission`,
`—` = public, `~` = optional auth.

### auth — `/v1/auth`
| Method | Path | Auth | Service |
| --- | --- | --- | --- |
| POST | `/phone-check` | — | `AuthService.check_phone` |
| POST | `/register` | — | `AuthService.register` |
| POST | `/login` | — | `AuthService.login` |
| POST | `/social/google` | — | `AuthService.google_login` |
| POST | `/complete-profile` | A | `UserService.update_profile` |
| POST | `/password` | A | `AuthService.set_password` |
| POST | `/staff-login` | — | `AuthService.staff_login` |
| POST | `/refresh` | R | `AuthService.refresh` |
| POST | `/logout` | A + R | `AuthService.logout` |
| POST | `/logout-all` | A | `AuthService.logout_all` |

Sign-in is two calls, not one: `/phone-check` decides which of `/register` and
`/login` the client shows next, and returns no token of its own. There is no
verification step — see DECISIONS.md Part 9 for what that costs and why the
optional password is where it is.

### users — `/v1/users`
`GET /me`, `PATCH /me`, `DELETE /me` (204), `GET|POST /me/devices`,
`GET /me/friends`, `GET /me/friend-requests`, `POST /me/friends`,
`POST /me/friends/{id}/accept`, `GET /me/recent-locations`,
`POST /me/recent-locations`. All `A`.

### localization / geo / catalog
`GET /v1/languages` —, `GET /v1/regions` —, `GET /v1/regions/{id}/districts` —,
`GET /v1/venue-types` —, `GET /v1/amenities` —. All take `get_language_id`.

### venues — customer `/v1/venues`
| Method | Path | Auth | Service |
| --- | --- | --- | --- |
| GET | `/search` | ~ | `VenueService.search` |
| GET | `/{venue_id}` | ~ | `VenueService.get_detail` |
| GET | `/{venue_id}/availability` | — | `AvailabilityService.blocked_dates` |
| GET | `/{venue_id}/tables` | — | `AvailabilityService.available_tables` |
| GET | `/{venue_id}/zones` | — | `VenueTableService.list_zones` |
| GET | `/{venue_id}/menu` | — | `MenuService.list_items` |
| GET | `/{venue_id}/menu/categories` | — | `MenuService.list_categories` |
| GET | `/{venue_id}/services` | — | `VenueServiceCatalogService.list_for_venue` |
| GET | `/{venue_id}/reviews` | — | `ReviewService.list_for_venue` |

### venues — staff `/v1/venue/venues`
`GET /` (branches), `GET /counts` (Jami/Aktiv/Yopiq), `GET /{id}`,
`PATCH /{id}` `P:branch.manage`, `PUT /{id}/working-hours` `P:branch.manage`,
`GET /{id}/tables`, `POST /{id}/tables/bulk` `P:branch.manage`,
`GET /{id}/zones`, `PATCH /{id}/onboarding/*` `P:branch.manage`.

### staff — `/v1/venue/staff`
`GET /` , `GET /counts`, `GET /roles`, `POST /invitations` `P:staff.manage`,
`PATCH /{staff_id}/active` `P:staff.manage`, `POST /invitations/accept` —.

### menu — staff `/v1/venue/menu`
`GET|POST /categories` (`P:menu.edit` on write), `GET|POST /items`
(`P:menu.edit`), `GET /items/{id}`, `PUT /items/{id}/branches` `P:menu.publish`.

### bookings — customer `/v1/bookings`
`POST /table`, `POST /hall`, `GET /`, `GET /{id}`, `GET /{id}/qr`,
`POST /{id}/cancel`. All `A`.

### bookings — staff `/v1/venue/bookings`
`GET /` (day queue), `POST /check-in` `P:bookings.confirm`,
`POST /{id}/check-out` `P:bookings.confirm`,
`GET /blocked-dates`.

### orders — staff `/v1/venue/orders`
`GET /table-board`, `GET /kitchen-queue`, `GET /`, `POST /` `P:orders.open`,
`GET /{id}`, `POST /{id}/items` `P:orders.add_items`,
`POST /{id}/payments` `P:orders.close`, `POST /{id}/close` `P:orders.close`,
`POST /{id}/cancel` `P:orders.close`, `GET /{id}/receipt`,
`POST /{id}/receipt/reprint` `P:orders.close`.

### subscriptions / reviews / engagement / analytics
`GET /v1/subscriptions/plans` —, `GET /v1/subscriptions/me` A;
`POST /v1/reviews` A, `GET /v1/reviews/venue/{venue_id}` —;
`GET|POST /v1/favorites` A, `DELETE /v1/favorites/{venue_id}` A,
`GET /v1/conversations` A, `GET|POST /v1/conversations/{id}/messages` A,
`POST /v1/conversations/{id}/read` A, `GET /v1/notifications` A,
`GET /v1/notifications/unread-count` A, `POST /v1/notifications/{id}/read` A,
`POST /v1/notifications/read-all` A;
`GET /v1/venue/analytics/dashboard` `P:reports.view`,
`GET /v1/venue/analytics/daily` `P:reports.view`,
`GET /v1/venue/analytics/revenue` `P:reports.view`.

### health — `/api/health`
Outside versioning. Build info plus a database ping.

## Routes the service layer cannot yet support

Specified in the task but with no service method behind them. Each is listed in
DECISIONS.md with the method it needs; none is stubbed, because a route that
returns a lie is worse than a route that is absent from the schema.

`POST /venue/venues` (venue create), `PATCH /{id}/status`, venue photos,
`POST /{id}/zones`, `POST /{id}/table-qrs`, `GET /venues/by-qr/{token}`,
`GET /{venue_id}/guest-tiers`, booking `confirm`/`reject`, booking
`receipt.pdf`, `GET /bookings/history`, blocked-slot writes, order item
update/delete/status, menu category/item update+delete, item variants and photo,
staff invitation revoke and `PATCH /{staff_id}`, review get/update/delete and
staff reply, subscription subscribe/cancel.

## Generated routes

105 operations across 93 paths. This table is produced from `app.openapi()` and
is the authoritative list; the sections above explain the shape, this says what
exists.

| Method | Path | operation_id |
| --- | --- | --- |
| DELETE | `/api/v1/favorites/{venue_id}` | `engagement_remove_favorite` |
| DELETE | `/api/v1/users/me` | `users_delete_me` |
| GET | `/api/health` | `health_check` |
| GET | `/api/v1/amenities` | `catalog_list_amenities` |
| GET | `/api/v1/bookings` | `bookings_list_mine` |
| GET | `/api/v1/bookings/{booking_id}` | `bookings_get_detail` |
| GET | `/api/v1/conversations` | `engagement_list_conversations` |
| GET | `/api/v1/conversations/{conversation_id}/messages` | `engagement_list_messages` |
| GET | `/api/v1/favorites` | `engagement_list_favorites` |
| GET | `/api/v1/languages` | `localization_list_languages` |
| GET | `/api/v1/notifications` | `engagement_list_notifications` |
| GET | `/api/v1/notifications/unread-count` | `engagement_unread_count` |
| GET | `/api/v1/regions` | `geo_list_regions` |
| GET | `/api/v1/regions/{region_id}/districts` | `geo_list_districts` |
| GET | `/api/v1/reviews/venue/{venue_id}` | `reviews_list_for_venue` |
| GET | `/api/v1/reviews/venue/{venue_id}/aggregate` | `reviews_aggregate_for_venue` |
| GET | `/api/v1/service-catalog` | `services_list_catalog` |
| GET | `/api/v1/subscriptions/me` | `subscriptions_get_mine` |
| GET | `/api/v1/subscriptions/plans` | `subscriptions_list_plans` |
| GET | `/api/v1/users/me` | `users_get_me` |
| GET | `/api/v1/users/me/devices` | `users_list_devices` |
| GET | `/api/v1/users/me/friend-requests` | `users_list_friend_requests` |
| GET | `/api/v1/users/me/friends` | `users_list_friends` |
| GET | `/api/v1/users/me/recent-locations` | `users_list_recent_locations` |
| GET | `/api/v1/venue-types` | `catalog_list_venue_types` |
| GET | `/api/v1/venue/analytics/daily` | `venue_analytics_daily` |
| GET | `/api/v1/venue/analytics/dashboard` | `venue_analytics_dashboard` |
| GET | `/api/v1/venue/analytics/revenue` | `venue_analytics_revenue` |
| GET | `/api/v1/venue/bookings` | `venue_bookings_list_day` |
| GET | `/api/v1/venue/bookings/blocked-dates` | `venue_bookings_blocked_dates` |
| GET | `/api/v1/venue/groups/me` | `venue_groups_get_mine` |
| GET | `/api/v1/venue/groups/{group_id}/branches` | `venue_groups_get_with_branches` |
| GET | `/api/v1/venue/menu/categories` | `venue_menu_list_categories` |
| GET | `/api/v1/venue/menu/items` | `venue_menu_list_items` |
| GET | `/api/v1/venue/menu/items/{item_id}` | `venue_menu_get_item` |
| GET | `/api/v1/venue/orders` | `venue_orders_list` |
| GET | `/api/v1/venue/orders/kitchen-queue` | `venue_orders_kitchen_queue` |
| GET | `/api/v1/venue/orders/table-board` | `venue_orders_table_board` |
| GET | `/api/v1/venue/orders/{order_id}` | `venue_orders_get_detail` |
| GET | `/api/v1/venue/orders/{order_id}/receipt` | `venue_orders_get_receipt` |
| GET | `/api/v1/venue/staff` | `venue_staff_list` |
| GET | `/api/v1/venue/staff/counts` | `venue_staff_counts` |
| GET | `/api/v1/venue/staff/roles` | `venue_staff_list_roles` |
| GET | `/api/v1/venue/venues` | `venue_venues_list` |
| GET | `/api/v1/venue/venues/counts` | `venue_venues_status_counts` |
| GET | `/api/v1/venue/venues/{venue_id}` | `venue_venues_get` |
| GET | `/api/v1/venue/venues/{venue_id}/tables` | `venue_venues_list_tables` |
| GET | `/api/v1/venue/venues/{venue_id}/zones` | `venue_venues_list_zones` |
| GET | `/api/v1/venues/search` | `venues_search` |
| GET | `/api/v1/venues/{venue_id}` | `venues_get_detail` |
| GET | `/api/v1/venues/{venue_id}/availability` | `venues_get_availability` |
| GET | `/api/v1/venues/{venue_id}/menu` | `venues_list_menu_items` |
| GET | `/api/v1/venues/{venue_id}/reviews` | `venues_list_reviews` |
| GET | `/api/v1/venues/{venue_id}/services` | `venues_list_services` |
| GET | `/api/v1/venues/{venue_id}/tables` | `venues_list_free_tables` |
| GET | `/api/v1/venues/{venue_id}/zones` | `venues_list_zones` |
| PATCH | `/api/v1/users/me` | `users_update_me` |
| PATCH | `/api/v1/venue/groups/{group_id}` | `venue_groups_update` |
| PATCH | `/api/v1/venue/staff/{staff_id}/active` | `venue_staff_set_active` |
| PATCH | `/api/v1/venue/venues/{venue_id}` | `venue_venues_update` |
| PATCH | `/api/v1/venue/venues/{venue_id}/onboarding/address` | `venue_venues_onboarding_address` |
| PATCH | `/api/v1/venue/venues/{venue_id}/onboarding/media-done` | `venue_venues_onboarding_media_done` |
| PATCH | `/api/v1/venue/venues/{venue_id}/onboarding/services-done` | `venue_venues_onboarding_services_done` |
| PATCH | `/api/v1/venue/venues/{venue_id}/onboarding/tables-done` | `venue_venues_onboarding_tables_done` |
| POST | `/api/v1/auth/complete-profile` | `auth_complete_profile` |
| POST | `/api/v1/auth/logout` | `auth_logout` |
| POST | `/api/v1/auth/logout-all` | `auth_logout_all` |
| POST | `/api/v1/auth/refresh` | `auth_refresh` |
| POST | `/api/v1/auth/login` | `auth_login` |
| POST | `/api/v1/auth/password` | `auth_set_password` |
| POST | `/api/v1/auth/phone-check` | `auth_phone_check` |
| POST | `/api/v1/auth/register` | `auth_register` |
| POST | `/api/v1/auth/social/google` | `auth_google_login` |
| POST | `/api/v1/auth/staff-login` | `auth_staff_login` |
| POST | `/api/v1/bookings/hall` | `bookings_create_hall_event` |
| POST | `/api/v1/bookings/table` | `bookings_create_table_reservation` |
| POST | `/api/v1/bookings/{booking_id}/cancel` | `bookings_cancel` |
| POST | `/api/v1/conversations` | `engagement_open_conversation` |
| POST | `/api/v1/conversations/{conversation_id}/messages` | `engagement_send_message` |
| POST | `/api/v1/conversations/{conversation_id}/read` | `engagement_mark_conversation_read` |
| POST | `/api/v1/favorites` | `engagement_toggle_favorite` |
| POST | `/api/v1/notifications/read-all` | `engagement_mark_all_notifications_read` |
| POST | `/api/v1/notifications/{notification_id}/read` | `engagement_mark_notification_read` |
| POST | `/api/v1/reviews` | `reviews_create` |
| POST | `/api/v1/users/me/devices` | `users_register_device` |
| POST | `/api/v1/users/me/friends` | `users_request_friend` |
| POST | `/api/v1/users/me/friends/{friendship_id}/accept` | `users_accept_friend` |
| POST | `/api/v1/users/me/recent-locations` | `users_remember_location` |
| POST | `/api/v1/venue/bookings/check-in` | `venue_bookings_check_in` |
| POST | `/api/v1/venue/bookings/{booking_id}/check-out` | `venue_bookings_check_out` |
| POST | `/api/v1/venue/menu/categories` | `venue_menu_create_category` |
| POST | `/api/v1/venue/menu/items` | `venue_menu_create_item` |
| POST | `/api/v1/venue/orders` | `venue_orders_open_table` |
| POST | `/api/v1/venue/orders/{order_id}/cancel` | `venue_orders_cancel` |
| POST | `/api/v1/venue/orders/{order_id}/close` | `venue_orders_close` |
| POST | `/api/v1/venue/orders/{order_id}/items` | `venue_orders_add_items` |
| POST | `/api/v1/venue/orders/{order_id}/payments` | `venue_orders_add_payment` |
| POST | `/api/v1/venue/orders/{order_id}/receipt/reprint` | `venue_orders_reprint_receipt` |
| POST | `/api/v1/venue/services` | `venue_services_create` |
| POST | `/api/v1/venue/staff/invitations` | `venue_staff_invite` |
| POST | `/api/v1/venue/staff/invitations/accept` | `venue_staff_accept_invitation` |
| POST | `/api/v1/venue/venues/{venue_id}/onboarding/finish` | `venue_venues_onboarding_finish` |
| POST | `/api/v1/venue/venues/{venue_id}/tables/bulk` | `venue_venues_create_tables_bulk` |
| PUT | `/api/v1/venue/menu/items/{item_id}/branches` | `venue_menu_set_item_branches` |
| PUT | `/api/v1/venue/venues/{venue_id}/working-hours` | `venue_venues_replace_working_hours` |
