"""Redis cache layer with multi-tier TTL strategies.

Caching strategy:
┌──────────────────────┬───────────┬────────────────────────────────┐
│ Data                 │ TTL       │ Why                            │
├──────────────────────┼───────────┼────────────────────────────────┤
│ Customer profiles    │ 5 min     │ Rarely changes, frequent reads │
│ Product catalog      │ 10 min    │ Static reference data          │
│ Order details        │ 2 min     │ Can change (refund status)     │
│ Knowledge base       │ 30 min    │ Almost never changes           │
│ Ticket results       │ 10 min    │ Hot reads after resolution     │
│ Audit entries        │ 1 min     │ Write-heavy, need freshness    │
└──────────────────────┴───────────┴────────────────────────────────┘

Pattern: Cache-aside (read: cache → DB, write: DB → invalidate cache)
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None

# TTL presets (seconds)
TTL_CUSTOMER = 300       # 5 min
TTL_PRODUCT = 600        # 10 min
TTL_ORDER = 120          # 2 min — changes on refund
TTL_KNOWLEDGE_BASE = 1800  # 30 min
TTL_TICKET_RESULT = 600  # 10 min — hot after resolution
TTL_AUDIT = 60           # 1 min — write-heavy

# Key prefixes
PREFIX_CUSTOMER = "cache:customer:"
PREFIX_CUSTOMER_EMAIL = "cache:customer_email:"
PREFIX_PRODUCT = "cache:product:"
PREFIX_ORDER = "cache:order:"
PREFIX_ORDERS_BY_CUSTOMER = "cache:orders_by_cust:"
PREFIX_KB = "cache:kb"
PREFIX_TICKET_RESULT = "cache:ticket_result:"
PREFIX_AUDIT = "cache:audit:"


async def init_cache() -> bool:
    global _redis
    settings = get_settings()

    if not settings.redis_url:
        logger.warning("REDIS_URL not set — caching disabled")
        return False

    try:
        _redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        await _redis.ping()
        logger.info("Redis connected: %s", settings.redis_url.split("@")[-1] if "@" in settings.redis_url else settings.redis_url)
        return True
    except Exception as e:
        logger.warning("Redis connection failed: %s — caching disabled", e)
        _redis = None
        return False


async def close_cache() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        logger.info("Redis connection closed")


def is_connected() -> bool:
    return _redis is not None


# ═══════════════════════════════════════════════════════════════
# Generic get/set/delete
# ═══════════════════════════════════════════════════════════════

async def cache_get(key: str) -> dict[str, Any] | list | str | None:
    if not _redis:
        return None
    try:
        raw = await _redis.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.debug("Cache get failed for %s: %s", key, e)
        return None


async def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    if not _redis:
        return
    try:
        ttl = ttl or get_settings().cache_ttl_seconds
        await _redis.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as e:
        logger.debug("Cache set failed for %s: %s", key, e)


async def cache_delete(key: str) -> None:
    if not _redis:
        return
    try:
        await _redis.delete(key)
    except Exception as e:
        logger.debug("Cache delete failed for %s: %s", key, e)


async def cache_delete_pattern(pattern: str) -> None:
    """Delete all keys matching a pattern (e.g. 'cache:order:*')."""
    if not _redis:
        return
    try:
        cursor = 0
        while True:
            cursor, keys = await _redis.scan(cursor, match=pattern, count=100)
            if keys:
                await _redis.delete(*keys)
            if cursor == 0:
                break
    except Exception as e:
        logger.debug("Cache pattern delete failed for %s: %s", pattern, e)


# ═══════════════════════════════════════════════════════════════
# Domain cache helpers
# ═══════════════════════════════════════════════════════════════

async def get_cached_customer_by_email(email: str) -> dict[str, Any] | None:
    return await cache_get(f"{PREFIX_CUSTOMER_EMAIL}{email.lower().strip()}")


async def set_cached_customer_by_email(email: str, data: dict[str, Any]) -> None:
    await cache_set(f"{PREFIX_CUSTOMER_EMAIL}{email.lower().strip()}", data, TTL_CUSTOMER)


async def get_cached_customer_by_id(cid: str) -> dict[str, Any] | None:
    return await cache_get(f"{PREFIX_CUSTOMER}{cid}")


async def set_cached_customer_by_id(cid: str, data: dict[str, Any]) -> None:
    await cache_set(f"{PREFIX_CUSTOMER}{cid}", data, TTL_CUSTOMER)


async def get_cached_order(order_id: str) -> dict[str, Any] | None:
    return await cache_get(f"{PREFIX_ORDER}{order_id}")


async def set_cached_order(order_id: str, data: dict[str, Any]) -> None:
    await cache_set(f"{PREFIX_ORDER}{order_id}", data, TTL_ORDER)


async def invalidate_order(order_id: str) -> None:
    """Invalidate order cache after a write (refund, status change)."""
    await cache_delete(f"{PREFIX_ORDER}{order_id}")


async def get_cached_orders_by_customer(cid: str) -> list[dict[str, Any]] | None:
    return await cache_get(f"{PREFIX_ORDERS_BY_CUSTOMER}{cid}")


async def set_cached_orders_by_customer(cid: str, data: list[dict[str, Any]]) -> None:
    await cache_set(f"{PREFIX_ORDERS_BY_CUSTOMER}{cid}", data, TTL_ORDER)


async def invalidate_customer_orders(cid: str) -> None:
    await cache_delete(f"{PREFIX_ORDERS_BY_CUSTOMER}{cid}")


async def get_cached_product(pid: str) -> dict[str, Any] | None:
    return await cache_get(f"{PREFIX_PRODUCT}{pid}")


async def set_cached_product(pid: str, data: dict[str, Any]) -> None:
    await cache_set(f"{PREFIX_PRODUCT}{pid}", data, TTL_PRODUCT)


async def get_cached_kb() -> str | None:
    return await cache_get(PREFIX_KB)


async def set_cached_kb(content: str) -> None:
    await cache_set(PREFIX_KB, content, TTL_KNOWLEDGE_BASE)


async def get_cached_ticket_result(ticket_id: str) -> dict[str, Any] | None:
    return await cache_get(f"{PREFIX_TICKET_RESULT}{ticket_id}")


async def set_cached_ticket_result(ticket_id: str, result: dict[str, Any]) -> None:
    await cache_set(f"{PREFIX_TICKET_RESULT}{ticket_id}", result, TTL_TICKET_RESULT)


async def get_cached_audit(ticket_id: str) -> dict[str, Any] | None:
    return await cache_get(f"{PREFIX_AUDIT}{ticket_id}")


async def set_cached_audit(ticket_id: str, data: dict[str, Any]) -> None:
    await cache_set(f"{PREFIX_AUDIT}{ticket_id}", data, TTL_AUDIT)
