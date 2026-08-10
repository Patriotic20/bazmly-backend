"""Shared Redis client and the Redis-backed token store.

One client for the process, created on startup and closed on shutdown — the same
rule as the HTTP client. Nothing here is imported by the sms package; the sms token
manager depends on the `TokenStore` protocol and this is one implementation of it.
"""

import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger("app.redis")

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """The process-wide client, created lazily."""
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis.url, encoding="utf-8", decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


class RedisTokenStore:
    """`TokenStore` backed by Redis, so refresh is single-flighted across workers.

    `redis.asyncio`'s lock is an async context manager with the same shape as
    `asyncio.Lock`, which is what lets the in-memory store stand in for it in tests
    without the token manager knowing the difference.
    """

    def __init__(self, client: aioredis.Redis | None = None) -> None:
        self._client = client or get_redis()

    async def get(self, key: str) -> str | None:
        value = await self._client.get(key)
        return value if isinstance(value, str) else None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        await self._client.set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    def lock(self, key: str, timeout_seconds: int) -> Any:
        # `blocking_timeout` bounds the wait so a queued caller fails fast rather
        # than hanging behind a crashed lock holder.
        return self._client.lock(key, timeout=timeout_seconds, blocking_timeout=timeout_seconds)
