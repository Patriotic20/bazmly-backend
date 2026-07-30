"""Availability cache.

Free slots derive from working hours, special days, tables, live bookings and
blocked slots. A pre-generated slots table would be millions of rows and stale on
every booking, so availability is computed and cached instead.

The cache is a protocol with an in-memory default. Nothing in the domain imports a
Redis client, so the suite runs without one, and swapping the implementation is a
settings change rather than a code change.
"""

import time
from typing import Any, Protocol

DEFAULT_TTL_SECONDS = 300


class AvailabilityCache(Protocol):
    async def get(self, key: str) -> Any | None: ...

    async def set(self, key: str, value: Any, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None: ...

    async def invalidate(self, prefix: str) -> None: ...


class InMemoryAvailabilityCache:
    """Process-local, TTL-aware. The default, and what tests run against.

    Correct but not shared between workers, so a second uvicorn process computes
    its own entries. That is a performance property, not a correctness one — every
    entry is derived data that can be recomputed.
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, Any]] = {}

    async def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            self._entries.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: Any, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._entries[key] = (time.monotonic() + ttl_seconds, value)

    async def invalidate(self, prefix: str) -> None:
        """Drop every entry under a prefix — used when a booking lands."""
        for key in [k for k in self._entries if k.startswith(prefix)]:
            self._entries.pop(key, None)


_cache: AvailabilityCache = InMemoryAvailabilityCache()


def get_availability_cache() -> AvailabilityCache:
    return _cache


def set_availability_cache(cache: AvailabilityCache) -> None:
    global _cache
    _cache = cache


def venue_availability_key(venue_id: int, day: str) -> str:
    return f"availability:{venue_id}:{day}"


def venue_availability_prefix(venue_id: int) -> str:
    return f"availability:{venue_id}:"
