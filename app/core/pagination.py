from typing import Annotated, Any

from fastapi import Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class PaginationParams:
    """Sahifalash oynasi: `limit` va `offset`."""

    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


# `arbitrary_types_allowed` is what lets repositories return `Page[Venue]` or
# `Page[VenueSearchRow]` — ORM models and plain dataclasses have no pydantic-core
# schema, and a repository has no business converting to a response schema. API
# layers keep returning `Page[SomePydanticSchema]`, which validates as before.
class Page[T](BaseModel):
    """Bir sahifa element va ular orasida harakatlanish uchun umumiy sonlar."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    total: int
    limit: int
    offset: int


async def paginate[T: BaseModel](
    session: AsyncSession,
    stmt: Select[Any],
    params: PaginationParams,
    schema: type[T],
) -> Page[T]:
    """Run ``stmt`` twice: once counting every row, once for the current window.

    Repositories build the ``Select`` and call this helper — there is no base
    repository to inherit pagination from.
    """
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    result = await session.execute(stmt.limit(params.limit).offset(params.offset))
    rows = result.scalars().all()

    return Page(
        items=[schema.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )
