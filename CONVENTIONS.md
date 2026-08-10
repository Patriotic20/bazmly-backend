# Conventions

These rules are not stylistic preferences. They are what keeps the codebase
navigable as modules multiply. Follow them exactly.

## Language

Content is **Uzbek only**. There are no `*_translations` tables — a name lives on
its own row (`venues.name`, `menu_items.name`). Do not add a `language_id`
parameter to a repository or service; if a second content language is ever needed
that is a schema decision, not a per-query one.

`languages` and `users.language_id` are the exception and are *not* content: they
are the account's interface-language preference, which the client reads to pick its
own strings.

User-facing prose — route summaries, descriptions, schema class docstrings, error
`message` values — is Uzbek, with ASCII apostrophes (`'`, never `’`). Machine-readable
values stay English: `code`, `operation_id`, tag names, `details` keys, enum values.

## 1. One thing per file

- **One model = one file.** Never two ORM models in one file. Association /
  many-to-many tables count as models: `user.py`, `role.py`, `user_role.py`
  are three separate files.
- **One repository = one file.**
- **One service = one file.**

## 2. No base repository, no generic CRUD

There is deliberately **no** `BaseRepository`, no abstract CRUD mixin, and no
shared generic repository class. Each repository is written out explicitly, even
when that means repeating the same five methods across ten files.

The repetition is the point: a repository stays readable in isolation, and a
change to one entity's persistence never silently changes another's.

What replaces the base class is [`app/core/pagination.py`](app/core/pagination.py):
a *helper*, not a parent. Repositories build a `Select` and hand it to
`paginate()`.

## 3. File vs folder

Exactly one of a kind in a module → a singular module file.
More than one → a plural package directory.

| Count | Model          | Repository            | Service            | Schema           |
| ----- | -------------- | --------------------- | ------------------ | ---------------- |
| 1     | `model.py`     | `repository.py`       | `service.py`       | `schema.py`      |
| 2+    | `models/`      | `repositories/`       | `services/`        | `schemas/`       |

Folder names are plural, single-file names are singular. Promote a file to a
package the moment a second one of its kind appears — do not stack two models
into `model.py`.

The spelling is **`schemas`**, never `schemes`.

## 4. Packages and re-exports

Every directory is a package with an `__init__.py`. A package's `__init__.py`
re-exports its public names, so this works:

```python
from app.modules.auth.models import Role, User
```

Keep `__all__` explicit and sorted.

## 5. Imports

All imports are absolute and rooted at `app.`:

```python
from app.core.config import settings  # yes
from ..core.config import settings  # no
```

## 6. Module skeleton

Every module — `auth`, `organization_structure`, and the `course`, `quiz` and
`psychology` modules that come later — has the identical shape:

```
app/modules/<module>/
├── __init__.py
├── api/
│   ├── __init__.py
│   ├── router.py            # re-exports v1_router and v2_router only
│   ├── v1/
│   │   ├── __init__.py
│   │   └── router.py
│   └── v2/
│       ├── __init__.py
│       └── router.py
├── models/         (or model.py)
├── repositories/   (or repository.py)
├── services/       (or service.py)
└── schemas/        (or schema.py)
```

`api/` always has both `v1/` and `v2/` packages plus a `router.py`, even when
`v2` has no endpoints yet.

To add a module, copy the `auth` skeleton verbatim, rename, and register its two
routers in [`app/core/router.py`](app/core/router.py). Nothing else in `core/`
should need to change.

## 7. Routing and versioning

URLs are `/api/v<n>/<module>/...` — **version before module** — while the `v1` /
`v2` packages live *inside* each module. The module's `api/router.py` only
re-exports the two version routers, so `core/router.py` has exactly one import
point per module.

`v2` routers are bare placeholders until there is a real v2. Do not duplicate v1
endpoints into v2.

`GET /api/health` lives on `main_router` and must never touch the database.

## 8. Dependency injection

The session is injected in the **endpoint**, passed to the **service**, and the
service constructs its **repository**.

```python
# endpoint
@router.get("/users")
async def list_users(
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    params: Annotated[PaginationParams, Depends()],
) -> Page[UserRead]:
    return await UserService(session).list_users(params)


# service
class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = UserRepository(session)

    async def create_user(self, data: UserCreate) -> UserRead:
        user = await self.repository.create(data)
        await self.session.commit()
        return UserRead.model_validate(user)
```

## 9. The service owns the transaction

**Repositories never call `commit()` or `rollback()`.** A repository may only
use `select`, `add`, `flush`, `refresh` and `delete`.

Only the service commits. This is what makes it possible for one service method
to call several repositories and still land as a single atomic transaction — a
repository that commits on its own destroys that guarantee, and the damage is
invisible until the day a second write is added next to it.

## 10. Primary keys

Integer primary keys everywhere, via the `IdIntPk` mixin. No UUIDs anywhere.

```python
class User(IdIntPk, TimestampMixin, Base):
    __tablename__ = "users"
```

## 11. Datetimes are naive UTC

asyncpg refuses to bind timezone-aware datetimes to columns declared
`TIMESTAMP WITHOUT TIME ZONE`. Every column here is naive, so tz-aware values
must be normalized before they reach a model.

UTC is enforced at three layers, all of which must hold:

1. **Connection level** — every connection's session `timezone` is pinned to
   UTC in `db_helper.py` via `connect_args={"server_settings": {"timezone": "UTC"}}`.
2. **Server default** — `func.timezone("UTC", func.now())` returns a
   `TIMESTAMP WITHOUT TIME ZONE` already converted to UTC, so it stays correct
   even if the Postgres server's own `TimeZone` is `Asia/Tashkent`.
3. **ORM level** — `default` / `onupdate` use `utcnow_naive()`, so ORM-created
   rows do not depend on the database at all.

**Any datetime entering from the API layer must pass through `to_naive_utc()`
before it reaches a model.**

### Known limitation

`updated_at` refreshes only on **ORM** updates. A raw `UPDATE` statement
(`session.execute(update(User)...)`, a psql session, a migration) will not touch
it. Fixing that properly needs a database trigger — **we deliberately do not
have one.** If you write a raw `UPDATE`, set `updated_at` yourself.

## 12. Errors

Raise the typed errors from [`app/core/exceptions.py`](app/core/exceptions.py)
(`NotFoundError`, `ConflictError`, `BadRequestError`, `UnauthorizedError`,
`ForbiddenError`) — not bare `HTTPException`.

Every error leaves the application in one envelope:

```json
{"code": "not_found", "message": "...", "details": {}, "request_id": "..."}
```

The catch-all handler logs the exception with its request id and returns a
generic 500. Never let an internal message reach the client.

## 13. Language

**User-facing prose is Uzbek (Latin). Everything else stays English.**

Uzbek: route `summary` / `description`, `openapi_tags` descriptions, the app
`summary` / `description`, Pydantic **schema class** docstrings, every error
`message`, and validator `ValueError` text. These are what a person reads in
Swagger or in a response body.

English: exception `code` values, `details` keys, `operation_id`, tag names, enum
values, field names, log messages, code comments, and **module and function
docstrings**.

Clients branch on `code`. `message` is display text and carries no contract.

The apostrophe is ASCII `'` — never `’`, never `ʻ`. Ruff's `RUF001`
(string literals) and `RUF002` (docstrings) reject the typographic forms, and the
seed migration already spells `To'yxona` and `Qo'riqchi` this way.

## 14. Typing

Type hints on everything — parameters, returns, and class attributes.
`uv run mypy app` must pass under `strict = true` with zero errors.
